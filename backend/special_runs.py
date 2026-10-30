"""Payroll THR dan Bonus Tahunan (user 30 Okt 2026): run sendiri di luar gaji bulanan.

Satu run = satu pembayaran (tanggal bayar sendiri), tersimpan sebagai periode dengan `run_type` "thr" / "bonus_tahunan".
Nominal per karyawan dari ROSY (komponen Tambahan Bulanan bulan dibayar) dan/atau diinput di RUSA; input RUSA menang.
Slip, ajukan/approve, batch BSI, dan PDF memakai jalur periode yang sudah ada (`/api/hr/periods/{pid}/...`); router ini hanya
memegang yang khas run khusus: membuat, menarik karyawan + nominal ROSY, mengisi nominal, dan rincian per karyawan.
Pajaknya: lihat engine.special_tax — selisih TER atas gaji bulan dibayar, dan Pasal 17 Desember menjumlahkan semuanya."""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import integrations
import signer as signer_mod
from core import db, now_iso, require_hr
from engine import SPECIAL_RUNS
from periods import BULAN, RUN_SPECIAL, run_type_of
from pipeline import get_period, process_special, special_amounts
from pymongo.errors import DuplicateKeyError
from routes_hr import EDITABLE_STATUSES, sync_employees, _account_blockers
from routes_tax import _rows_from_upload, _num

router = APIRouter(prefix="/api/hr/special-runs", dependencies=[Depends(require_hr)])

KODE = {"thr": "THR", "bonus_tahunan": "BONUS_TAHUNAN"}


class SpecialIn(BaseModel):
    run_type: str
    pay_date: str                 # tanggal dibayar: menentukan masa pajak (bukan tahun bonus itu diperoleh)
    title: Optional[str] = None   # "Idul Fitri 1448 H", "2026"; kosong = bulan & tahun dibayar


class AmountItem(BaseModel):
    employee_id: str
    nominal: Optional[float] = None   # None = hapus input RUSA (kembali ke nominal ROSY)


class AmountsIn(BaseModel):
    items: list[AmountItem]


async def _special(pid: str) -> dict:
    period = await get_period(pid)
    if run_type_of(period) not in RUN_SPECIAL:
        raise HTTPException(404, "Bukan run THR / Bonus Tahunan")
    return period


def _editable(period: dict):
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Run sedang direview Manager atau sudah dikunci")


@router.get("")
async def list_runs(run_type: str):
    if run_type not in RUN_SPECIAL:
        raise HTTPException(400, "run_type harus thr atau bonus_tahunan")
    periods = await db.payroll_periods.find({"run_type": run_type}, {"_id": 0, "review_history": 0}) \
        .sort("payment_date", -1).to_list(100)
    for p in periods:
        agg = [r async for r in db.payslips.aggregate([
            {"$match": {"payroll_period_id": p["id"]}},
            {"$group": {"_id": None, "n": {"$sum": 1}, "nominal": {"$sum": "$gross_earnings"},
                        "pph21": {"$sum": "$pph21_withheld"}, "thp": {"$sum": "$take_home_pay"}}}])]
        p["summary"] = {"slips": agg[0]["n"], "nominal": agg[0]["nominal"], "pph21": agg[0]["pph21"],
                        "thp": agg[0]["thp"]} if agg else {"slips": 0, "nominal": 0, "pph21": 0, "thp": 0}
    return periods


@router.post("")
async def create_run(body: SpecialIn):
    """Membuat run dan langsung menarik karyawan + nominal ROSY bulan dibayarnya, seperti periode gaji."""
    if body.run_type not in RUN_SPECIAL:
        raise HTTPException(400, "run_type harus thr atau bonus_tahunan")
    try:
        paid = date.fromisoformat(body.pay_date)
    except ValueError:
        raise HTTPException(400, "Tanggal bayar harus berformat YYYY-MM-DD")
    label = SPECIAL_RUNS[body.run_type][0]
    title = (body.title or "").strip() or f"{BULAN[paid.month - 1]} {paid.year}"
    data = {"id": str(uuid.uuid4()), "run_type": body.run_type, "title": title, "period_name": f"{label} {title}",
            "start_date": body.pay_date, "end_date": body.pay_date, "payment_date": body.pay_date,
            "bulan": body.pay_date[:7], "status": "draft", "approved_by": None, "approved_at": None,
            "created_at": now_iso(), "employee_ids": [], "employee_count": 0, "attendance_synced_at": None}
    try:
        await db.payroll_periods.insert_one({**data})
    except DuplicateKeyError:
        raise HTTPException(409, f"Run {label} untuk {BULAN[paid.month - 1]} {paid.year} sudah ada")
    try:
        await _sync(data["id"])
    except HTTPException as e:
        return {**await get_period(data["id"]), "sync_error": e.detail}
    return await get_period(data["id"])


async def _sync(pid: str) -> int:
    period = await _special(pid)
    _editable(period)
    ids, meta = await sync_employees(period["bulan"])
    emps = await db.employees.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "rosy_employee_id": 1}).to_list(5000)
    by_rosy = {e["rosy_employee_id"]: e["id"] for e in emps if e.get("rosy_employee_id")}
    signer = meta.get("penandatangan")
    await signer_mod.remember(signer, meta.get("company"))
    kode = KODE[run_type_of(period)]
    # hanya nominal ROSY yang diganti ulang; input RUSA (special_inputs) tidak tersentuh sinkron
    await db.period_components.delete_many({"payroll_period_id": pid})
    docs = [{"id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": by_rosy[rid], "kode": kode,
             "nominal": comps[kode], "synced_at": now_iso()}
            for rid, comps in (meta.get("components") or {}).items() if rid in by_rosy and comps.get(kode)]
    if docs:
        await db.period_components.insert_many(docs)
    # attendance_synced_at = penanda "sinkron ROSY berhasil" yang dicek Ajukan / Lock & Approve (routes_hr._ensure_synced)
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "employee_ids": ids, "employee_count": len(ids), "employees_synced_at": now_iso(),
        "employees_source": integrations.mode("ROSY"), "employees_skipped": meta.get("dilewati") or [],
        "company": meta.get("company"), "signer": signer, "attendance_synced_at": now_iso(),
        "last_sync_at": now_iso(), "rosy_nominal_count": len(docs)}, "$unset": {"last_sync_error": ""}})
    return await process_special(await get_period(pid))


@router.post("/{pid}/sync")
async def sync_run(pid: str):
    return {"processed": await _sync(pid)}


@router.put("/{pid}/amounts")
async def save_amounts(pid: str, body: AmountsIn):
    """Mengisi nominal di RUSA (menimpa ROSY); nominal null menghapus isian RUSA. Slip dihitung ulang."""
    period = await _special(pid)
    _editable(period)
    population = set(period.get("employee_ids") or [])
    for it in body.items:
        if it.employee_id not in population:
            raise HTTPException(400, "Karyawan tidak ada di populasi run ini")
        if it.nominal is None:
            await db.special_inputs.delete_one({"payroll_period_id": pid, "employee_id": it.employee_id})
        elif it.nominal < 0:
            raise HTTPException(400, "Nominal tidak boleh negatif")
        else:
            await db.special_inputs.update_one(
                {"payroll_period_id": pid, "employee_id": it.employee_id},
                {"$set": {"nominal": round(it.nominal), "updated_at": now_iso()},
                 "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    return {"processed": await process_special(period)}


@router.post("/{pid}/import")
async def import_amounts(pid: str, file: UploadFile = File(...)):
    """Unggah .xlsx / .csv berkolom `nik` dan `nominal`. Semua baris dicek dulu; satu baris salah = tidak ada yang tersimpan."""
    period = await _special(pid)
    _editable(period)
    try:
        rows = _rows_from_upload(file.filename or "", await file.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Berkas tidak terbaca: {e}")
    emps = {e["nik"]: e["id"] async for e in db.employees.find(
        {"id": {"$in": period.get("employee_ids") or []}}, {"_id": 0, "id": 1, "nik": 1})}
    ok, problems = [], []
    for i, r in enumerate(rows, start=2):
        nik = str(r.get("nik") or "").strip()
        if nik.endswith(".0"):
            nik = nik[:-2]
        try:
            nominal = _num(r.get("nominal"))
        except ValueError:
            problems.append(f"Baris {i}: nominal tidak terbaca")
            continue
        if nik not in emps:
            problems.append(f"Baris {i}: NIK {nik or '(kosong)'} tidak ada di populasi run ini")
        elif nominal < 0:
            problems.append(f"Baris {i}: nominal negatif")
        else:
            ok.append((emps[nik], nominal))
    if problems:
        raise HTTPException(422, "Berkas tidak disimpan: " + "; ".join(problems[:10]) +
                            (f" (+{len(problems) - 10} lagi)" if len(problems) > 10 else ""))
    for eid, nominal in ok:
        await db.special_inputs.update_one(
            {"payroll_period_id": pid, "employee_id": eid},
            {"$set": {"nominal": round(nominal), "updated_at": now_iso()}, "$setOnInsert": {"id": str(uuid.uuid4())}},
            upsert=True)
    return {"imported": len(ok), "processed": await process_special(period)}


@router.get("/{pid}")
async def run_detail(pid: str):
    period = await _special(pid)
    emps = await db.employees.find({"id": {"$in": period.get("employee_ids") or []}}, {"_id": 0}).sort("nik", 1).to_list(5000)
    amounts = await special_amounts(period)
    rosy = {d["employee_id"]: d["nominal"] async for d in db.period_components.find(
        {"payroll_period_id": pid}, {"_id": 0, "employee_id": 1, "nominal": 1})}
    manual = {d["employee_id"]: d["nominal"] async for d in db.special_inputs.find(
        {"payroll_period_id": pid}, {"_id": 0, "employee_id": 1, "nominal": 1})}
    slips = {s["employee_id"]: s async for s in db.payslips.find({"payroll_period_id": pid}, {"_id": 0, "bpjs": 0})}
    rows = []
    for e in emps:
        nominal, source = amounts.get(e["id"], (0, None))
        s = slips.get(e["id"])
        rows.append({"employee_id": e["id"], "nik": e["nik"], "name": e["name"], "department": e.get("department"),
                     "rosy_nominal": rosy.get(e["id"]), "manual_nominal": manual.get(e["id"]), "nominal": nominal,
                     "source": source, "slip": s})
    got = [r["slip"] for r in rows if r["slip"]]
    blockers = await _account_blockers(got)
    sources = [(r["slip"] or {}).get("special_tax", {}).get("baseline_source", "") for r in rows if r["slip"]]
    summary = {
        "employees": len(rows), "slips": len(got), "nominal": sum(s["gross_earnings"] for s in got),
        "pph21": sum(s["pph21_withheld"] for s in got), "thp": sum(s["take_home_pay"] for s in got),
        # dasar pajaknya: slip gaji bulan dibayar (tepat), slip gaji terakhir (perkiraan), atau tidak ada
        "baseline_exact": sum(1 for x in sources if x == "slip_bulan_ini"),
        "baseline_estimated": sum(1 for x in sources if x.startswith("slip_terakhir")),
        "baseline_none": sum(1 for x in sources if x == "tidak_ada"),
        "from_rosy": sum(1 for r in rows if r["source"] == "rosy"), "from_rusa": sum(1 for r in rows if r["source"] == "rusa"),
        "final_tax_month": period["bulan"][5:7] == "12"}
    return {"period": period, "rows": rows, "summary": summary, "bank_blockers": blockers,
            "signer_status": signer_mod.status(period.get("signer"))}
