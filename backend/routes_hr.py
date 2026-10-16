import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core import db, now_iso, require_hr, require_manager, actor, get_configs, DEFAULT_CONFIGS, CONFIG_CHOICES
from pipeline import (get_period, get_employee, period_logs, build_slip, recalc_and_save, process_period,
                      approve_slip, queue_delivery, ADJ_KEYS)
from pdf_service import render_payslip
from labels import position_allowance_label
from periods import BULAN, payroll_month, period_name_for, validate_dates, overlaps
from bank_batch import approval_blockers
import integrations
import signer as signer_mod
import verify

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])


class PeriodIn(BaseModel):
    period_name: Optional[str] = None  # ignored when the period lies within one month (auto "Oktober 2026")
    start_date: str
    end_date: str
    payment_date: Optional[str] = None


class AdjustIn(BaseModel):
    overtime_hours: float = 0
    kpi_incentive: float = 0
    additional_bonus: float = 0
    other_deductions: float = 0
    adjustment_notes: str = ""


@router.get("/dashboard")
async def dashboard():
    periods = await db.payroll_periods.find({}, {"_id": 0}).sort("start_date", -1).to_list(50)
    latest = periods[0] if periods else None
    stats = {"employees": await db.employees.count_documents({}), "periods": len(periods), "latest_period": latest}
    if latest:
        slips = await db.payslips.find({"payroll_period_id": latest["id"]}, {"_id": 0}).to_list(2000)
        stats.update(total_thp=sum(s["take_home_pay"] for s in slips), total_pph21=sum(s["pph21_amount"] for s in slips),
                     total_gross=sum(s["gross_earnings"] for s in slips),
                     total_bpjs_kes=sum(s["iuran_bpjs_kes_total"] for s in slips),
                     total_bpjs_tk=sum(s["iuran_bpjs_tk_total"] for s in slips),
                     pending=sum(1 for s in slips if s["status"] != "approved"),
                     approved=sum(1 for s in slips if s["status"] == "approved"))
    return stats


def _tanggal(iso: Optional[str]) -> str:
    return f"{int(iso[8:10])} {BULAN[int(iso[5:7]) - 1]} {iso[:4]}" if iso else "-"


async def _present_days(period: dict, emp_ids: list) -> dict:
    """Days actually worked in the period per employee (attendance logs marked present)."""
    rows = db.attendance_daily_logs.aggregate([
        {"$match": {"employee_id": {"$in": emp_ids}, "leave_type": "present",
                    "work_date": {"$gte": period["start_date"], "$lte": period["end_date"]}}},
        {"$group": {"_id": "$employee_id", "n": {"$sum": 1}}}])
    return {r["_id"]: r["n"] async for r in rows}


def _prorata_note(slip: dict, emp: dict, period: dict, maternity_days: int, present_days: int) -> Optional[str]:
    """Why a slip is not a full month's pay as "fakta — akibat", or None (user 10 Oct 2026: prorata cases — joining or
    leaving inside the period, maternity leave that starts or ends inside it, prolonged illness — not the alfa/izin fines,
    which are attendance penalties). Since 15 Oct 2026 RUSA prorates the first three itself (engine.prorata, slip
    "prorata"): the note says by how much. A slip calculated before that still says "cek prorata" until Fetch Data
    Terbaru recalculates it."""
    start, end = period["start_date"], period["end_date"]
    join, leave = emp.get("join_date"), emp.get("exit_date")
    pr = slip.get("prorata")
    if pr:
        if pr["basic_factor"] >= 1 and pr["attendance_factor"] >= 1:
            return None  # 25 hari kerja atau lebih di masa aktifnya: tetap dibayar penuh
        if pr["kind"] == "cuti_melahirkan":
            return (f"cuti melahirkan {pr['maternity_days']} hari, masuk kerja {present_days} hari — Tunjangan Kehadiran "
                    f"diprorata {pr['attendance_days']}/{pr['divisor']} hari kerja")
        when = {"masuk": f"masuk {_tanggal(join)}", "keluar": f"keluar {_tanggal(leave)}",
                "masuk_keluar": f"masuk {_tanggal(join)}, keluar {_tanggal(leave)}"}[pr["kind"]]
        return f"{when}, di tengah periode — gaji diprorata {pr['work_days']}/{pr['divisor']} hari kerja"
    if join and start < join <= end:
        return f"masuk {_tanggal(join)}, di tengah periode — cek prorata"
    if leave and start <= leave < end:
        return f"keluar {_tanggal(leave)}, di tengah periode — cek prorata"
    if maternity_days and present_days:
        return f"cuti melahirkan {maternity_days} hari, masuk kerja {present_days} hari — cek prorata"
    if (slip.get("wage_multiplier") or 1) < 1:
        return f"sakit berkepanjangan — gaji pokok {round(slip['wage_multiplier'] * 100)}%"
    return None


# totals on the Dashboard's nominal cards: key -> slip field
PAYROLL_TOTALS = (("thp", "take_home_pay"), ("pph21", "pph21_amount"), ("bpjs_kes", "iuran_bpjs_kes_total"),
                  ("bpjs_tk", "iuran_bpjs_tk_total"))


def _totals(slips: list) -> dict:
    return {f"total_{k}": sum(s.get(f) or 0 for s in slips) for k, f in PAYROLL_TOTALS}


def _delta(now: float, before: float) -> dict:
    """Change against the period before (Dashboard cards, user 14 Oct 2026). pct is None when there is nothing to compare
    with (the period before has no slips / employees), so the card shows no arrow instead of an infinite percentage."""
    return {"prev": before, "diff": now - before, "pct": round((now - before) / before * 100, 1) if before else None}


@router.get("/dashboard/employees")
async def dashboard_employees(pid: Optional[str] = None):
    """Who needs a look before payday (user request 10 Oct 2026): the period's headcount, who joined and who left,
    who is not paid this period or not in full, and employee data to check. Latest period by default.

    13 Oct 2026: the "Absensi perlu dicek" group is gone (alfa/izin and missing attendance are no longer listed or
    counted here). "Tidak ikut digaji" lists the employees on unpaid leave (the same people as the Unpaid card on the
    period page), no longer the employees without a Kontrak Gaji. The cards count those and the employees whose ROSY
    data is incomplete (rekening, NPWP, ...).

    14 Oct 2026: maternity leave is paid (gapok only when it covers the whole period), so those employees are "Gaji
    tidak penuh", not "Tidak ikut digaji". `compare` sets the nominal cards and the headcount against the period before
    (None for the first period). "Rekening belum siap" (first group): the accounts that block "Ajukan ke Manager" and
    Lock & Approve — no account number, no account name or not BSI (bank_batch.approval_blockers)."""
    periods = await db.payroll_periods.find({}, {"_id": 0, "review_history": 0}).sort("start_date", -1).to_list(100)
    period = next((p for p in periods if p["id"] == pid), None) if pid else (periods[0] if periods else None)
    if not period:
        if pid:
            raise HTTPException(404, "Periode tidak ditemukan")
        return {"period": None, "counts": {}, "groups": [], "payroll": None, "compare": None}
    start, end = period["start_date"], period["end_date"]
    ids = period.get("employee_ids") or []
    fields = {"_id": 0, "id": 1, "rosy_employee_id": 1, "nik": 1, "name": 1, "join_date": 1, "exit_date": 1,
              "payroll_status": 1, "data_issues": 1, "department": 1}
    emps = {e["id"]: e async for e in db.employees.find({"id": {"$in": ids}}, fields)}
    slips = {s["employee_id"]: s async for s in db.payslips.find({"payroll_period_id": period["id"]}, {
        "_id": 0, "employee_id": 1, "employee.nik": 1, "employee.name": 1, "status": 1, "payroll_status": 1,
        "wage_multiplier": 1, "maternity_basic_only": 1, "discipline.presence_by_type": 1, "prorata": 1, "take_home_pay": 1,
        "pph21_amount": 1, "iuran_bpjs_kes_total": 1, "iuran_bpjs_tk_total": 1})}

    def item(e: dict, note: str) -> dict:
        return {"employee_id": e.get("id"), "nik": e.get("nik"), "name": e.get("name"), "note": note,
                "has_slip": e.get("id") in slips}

    # left: a ROSY exit date inside the period, or in the previous period but no longer sent by ROSY
    left = [item(e, f"keluar {_tanggal(e['exit_date'])}") for e in emps.values()
            if e.get("exit_date") and start <= e["exit_date"] <= end]
    prev = next((p for p in periods if p["start_date"] < start), None)
    if prev:
        gone = [i for i in prev.get("employee_ids") or [] if i not in set(ids)]
        async for e in db.employees.find({"id": {"$in": gone}}, fields):
            # user 14 Oct 2026: no "tidak dikirim ROSY" wording on this card; what RUSA knows is that ROSY has no exit date
            why = f"keluar {_tanggal(e['exit_date'])}" if e.get("exit_date") else "tanpa tanggal keluar di ROSY"
            left.append(item(e, f"{why} — ada di {prev['period_name']}, tidak ada di periode ini"))
    new = [item(e, f"mulai {_tanggal(e['join_date'])}") for e in emps.values()
           if e.get("join_date") and start <= e["join_date"] <= end]
    # Not paid: only ROSY's is_paid switched off (unpaid = cuti di luar tanggungan, everything Rp 0) — the same people as
    # the period page's Unpaid card. Maternity leave is paid, so it is not "Tidak ikut digaji" (user 14 Oct 2026): a leave
    # that covers the whole period pays gapok only (slip flag maternity_basic_only) and is listed under "Gaji tidak
    # penuh"; one that starts or ends inside the period is a prorata case below. Employees without a Kontrak Gaji (HAM
    # meta.dilewati) are not listed here any more (user 13 Oct 2026): ROSY will require salary data for every new
    # employee
    not_paid, partial, unpaid = [], [], set()
    present = await _present_days(period, ids)
    for e in emps.values():
        s = slips.get(e["id"]) or {}
        if (s.get("payroll_status") or e.get("payroll_status")) == "unpaid_leave":
            unpaid.add(e["id"])
            not_paid.append(item(e, "cuti di luar tanggungan — upah & tunjangan Rp 0"))
            continue
        # a prorated maternity month no longer gives its leave days a poin (15 Oct 2026): the slip's prorata counts them
        maternity_days = ((s.get("prorata") or {}).get("maternity_days")
                          or ((s.get("discipline") or {}).get("presence_by_type") or {}).get("maternity_leave", 0))
        if s.get("maternity_basic_only"):
            partial.append(item(e, f"cuti melahirkan {maternity_days} hari — dibayarkan gaji pokok saja"))
            continue
        # a maternity leave that starts or ends inside the period is also a prorata case, as on the period page
        note = _prorata_note(s, e, period, maternity_days, present.get(e["id"], 0))
        if note:
            partial.append(item(e, note))
    # one employee counts once, however many things are missing
    data = [{**item(e, ""), "issues": e["data_issues"]} for e in emps.values() if e.get("data_issues")]
    # accounts that block submitting and Lock & Approve (user 14 Oct 2026), listed first: the period page banner's list
    bank = [item(emps.get(b["employee_id"]) or {"id": b["employee_id"], "nik": b["nik"], "name": b["name"]},
                 f"{', '.join(p['kind'] for p in b['problems'])} — payroll belum bisa diproses")
            for b in await _account_blockers(list(slips.values()))]

    groups = [("bank", "Rekening belum siap", bank), ("left", "Karyawan keluar", left), ("new", "Karyawan baru", new),
              ("not_paid", "Tidak ikut digaji", not_paid), ("partial", "Gaji tidak penuh", partial),
              ("data", "Data karyawan belum lengkap", data)]
    sl = list(slips.values())
    payroll = {"slips": len(sl), "approved": sum(1 for s in sl if s.get("status") == "approved"), **_totals(sl)}
    # against the period before this one (arrows on the cards, user 14 Oct 2026); nothing for the first period
    compare = None
    if prev:
        before = _totals(await db.payslips.find({"payroll_period_id": prev["id"]},
                                                {"_id": 0, **{f: 1 for _, f in PAYROLL_TOTALS}}).to_list(2000))
        compare = {"period_name": prev["period_name"],
                   "in_period": _delta(len(ids), len(prev.get("employee_ids") or [])),
                   **{k: _delta(payroll[k], v) for k, v in before.items()}}
    return {
        "period": {k: period.get(k) for k in ("id", "period_name", "status", "start_date", "end_date", "payment_date",
                                              "last_sync_at", "last_sync_error", "employees_synced_at")},
        "counts": {"in_period": len(ids), "new": len(new), "left": len(left), "unpaid": len(unpaid), "data": len(data)},
        "groups": [{"key": k, "title": t, "items": sorted(rows, key=lambda i: (i.get("name") or "").casefold())}
                   for k, t, rows in groups],
        "payroll": payroll, "compare": compare,
    }


@router.get("/notifications")
async def notifications(user: dict = Depends(require_hr)):
    if user["role"] == "manager_hrd":
        q, kind = {"status": "pending_approval"}, "submitted"
    else:
        q, kind = {"status": "revision"}, "rejected"
    periods = await db.payroll_periods.find(q, {"_id": 0}).sort("start_date", -1).to_list(100)
    return [{"kind": kind, "period_id": p["id"], "period_name": p["period_name"],
             "by": (p.get("submitted_by_name") or p.get("submitted_by")) if kind == "submitted"
             else (p.get("rejected_by_name") or p.get("rejected_by")),
             "at": p.get("submitted_at") if kind == "submitted" else p.get("rejected_at"),
             "reason": p.get("rejection_reason") if kind == "rejected" else None} for p in periods]


@router.get("/configs")
async def list_configs():
    docs = await db.payroll_configs.find({}, {"_id": 0}).sort("config_key", 1).to_list(100)
    # a config with a fixed set of values (PPH21_BASIS) says which, so the page offers a choice instead of free text
    return [{**d, "choices": list(CONFIG_CHOICES[d["config_key"]])} if d["config_key"] in CONFIG_CHOICES else d
            for d in docs]


@router.put("/configs", dependencies=[Depends(require_manager)])
async def update_configs(body: dict):
    for k, v in body.items():
        if k not in DEFAULT_CONFIGS:
            raise HTTPException(400, f"Config tidak dikenal: {k}")
        if k == "CSV_DELIMITER" and str(v) not in (",", ";", "|", "tab"):
            raise HTTPException(400, "Pemisah CSV harus , ; | atau tab")
        if k == "SLIP_VERIFY_BASE_URL" and str(v).strip() and not verify.clean_base(str(v)):
            raise HTTPException(400, "Alamat verifikasi slip harus diawali http:// atau https://, mis. https://rusa.rumat.id")
        if k in CONFIG_CHOICES and str(v) not in CONFIG_CHOICES[k]:
            raise HTTPException(400, f"{k} harus salah satu dari: {', '.join(CONFIG_CHOICES[k])}")
        await db.payroll_configs.update_one({"config_key": k}, {"$set": {"config_value": str(v)}})
    return await list_configs()


@router.get("/signer")
async def slip_signer():
    """Slip signer from ROSY for the Config page: name, position, and where the QR on the slips points."""
    return await signer_mod.current()


@router.post("/signer/refresh", dependencies=[Depends(require_manager)])
async def refresh_slip_signer():
    if integrations.mode("ROSY") != "live":
        raise HTTPException(400, "Penandatangan hanya bisa diambil dari ROSY: HAM_API_URL belum diatur")
    try:
        return await signer_mod.refresh()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil penandatangan dari ROSY: {e}")


@router.get("/employees")
async def list_employees():
    return await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(2000)


async def sync_employees(periode: str) -> tuple:
    """Fetch master karyawan & gaji dari ROSY (HAM); upsert by rosy_employee_id. Returns (employee ids, meta).

    HAM's nik is not unique, so it is never the key. Employees created before rosy_employee_id existed
    are adopted once by nik."""
    try:
        rows, meta = await integrations.fetch_employees(periode)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data karyawan dari ROSY: {e}")
    ids = []
    for r in rows:
        existing = await db.employees.find_one({"rosy_employee_id": r["rosy_employee_id"]}, {"_id": 0, "id": 1}) or \
            await db.employees.find_one({"rosy_employee_id": {"$exists": False}, "nik": r["nik"]}, {"_id": 0, "id": 1})
        eid = existing["id"] if existing else str(uuid.uuid4())
        await db.employees.update_one({"id": eid}, {"$set": {**r, "source": "rosy", "in_rosy": True,
                                                            "synced_at": now_iso()},
                                                   "$setOnInsert": {"created_at": now_iso()}}, upsert=True)
        ids.append(eid)
    # Employees ROSY no longer returns (resigned, moved company, lost their salary contract) stay for history
    # but are flagged, so the list never silently mixes them with the current payroll population
    gone = await db.employees.update_many(
        {"source": "rosy", "rosy_employee_id": {"$nin": [r["rosy_employee_id"] for r in rows]}},
        {"$set": {"in_rosy": False}})
    await db.sync_status.update_one({"key": "employees"}, {"$set": {
        "key": "employees", "synced_at": now_iso(), "periode": periode, "source": integrations.mode("ROSY"),
        "count": len(ids), "skipped": meta.get("dilewati") or [], "company": meta.get("company"),
        "not_in_rosy": await db.employees.count_documents({"source": "rosy", "in_rosy": False}),
        "newly_not_in_rosy": gone.modified_count,
        "data_issues": dict(Counter(i for r in rows for i in r.get("data_issues") or []))}}, upsert=True)
    return ids, meta


@router.get("/employees/sync-status")
async def employees_sync_status():
    return await db.sync_status.find_one({"key": "employees"}, {"_id": 0}) or {}


@router.post("/employees/sync")
async def sync_employees_now(periode: Optional[str] = None):
    """Manual sync from the Karyawan menu; defaults to the current month (WIB)."""
    periode = periode or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periode):
        raise HTTPException(400, "Format periode harus YYYY-MM")
    await sync_employees(periode)
    return await employees_sync_status()


@router.get("/attendance")
async def list_attendance(employee_id: str, start: str, end: str):
    return await db.attendance_daily_logs.find(
        {"employee_id": employee_id, "work_date": {"$gte": start, "$lte": end}}, {"_id": 0}
    ).sort("work_date", 1).to_list(400)


@router.get("/periods")
async def list_periods():
    return await db.payroll_periods.find({}, {"_id": 0}).sort("start_date", -1).to_list(100)


@router.post("/periods")
async def create_period(body: PeriodIn):
    """Creates the period and immediately syncs everything from ROSY, so the slips are there at once.
    One period per month (ROSY pays 1 slip per employee per month); dates may not overlap another period."""
    validate_dates(body.start_date, body.end_date)
    name = period_name_for(body.start_date, body.end_date) or (body.period_name or "").strip()
    if not name:
        raise HTTPException(400, "Periode lintas bulan wajib diberi nama")
    bulan = payroll_month(body.start_date)
    async for other in db.payroll_periods.find({}, {"_id": 0, "period_name": 1, "bulan": 1, "start_date": 1,
                                                    "end_date": 1}):
        if other.get("bulan") == bulan:
            raise HTTPException(409, f"Periode {other['period_name']} sudah ada — satu bulan hanya satu periode")
        if overlaps(body.start_date, body.end_date, other):
            raise HTTPException(409, f"Tanggal bertumpuk dengan periode {other['period_name']}")
    data = body.model_dump()
    data.update(id=str(uuid.uuid4()), period_name=name, bulan=bulan, status="draft", approved_by=None,
                approved_at=None, created_at=now_iso(), employee_ids=[], employee_count=0, attendance_synced_at=None)
    try:
        await db.payroll_periods.insert_one({**data})
    except DuplicateKeyError:
        raise HTTPException(409, f"Periode {name} sudah ada — satu bulan hanya satu periode")
    try:
        result = await sync_period(data["id"])
    except HTTPException as e:
        # the draft stays; "Fetch Data Terbaru" retries
        return {**await get_period(data["id"]), "sync_error": e.detail}
    return {**await get_period(data["id"]), "sync": result}


SYNC_STALE = timedelta(minutes=10)


@router.post("/periods/{pid}/fetch-attendance")
async def sync_now(pid: str):
    """Button "Fetch Data Terbaru" (period page): employees & salary, attendance, overtime and Tambahan Bulanan."""
    return await sync_period(pid)


async def sync_period(pid: str) -> dict:
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci")
    now = datetime.now(timezone.utc)
    lock = await db.payroll_periods.update_one(
        {"id": pid, "$or": [{"sync_running_since": None}, {"sync_running_since": {"$exists": False}},
                            {"sync_running_since": {"$lt": (now - SYNC_STALE).isoformat()}}]},
        {"$set": {"sync_running_since": now.isoformat()}})
    if not lock.modified_count:
        raise HTTPException(409, "Sinkron periode ini sedang berjalan. Tunggu sebentar lalu muat ulang")
    try:
        result = await _sync(pid)
    except HTTPException as e:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"last_sync_error": e.detail, "last_sync_at": now_iso()}})
        raise
    finally:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"sync_running_since": None}})
    await db.payroll_periods.update_one({"id": pid}, {"$set": {"last_sync_at": now_iso()}, "$unset": {"last_sync_error": ""}})
    return result


async def _sync(pid: str) -> dict:
    period = await get_period(pid)
    # One button pulls everything fresh from ROSY: salary, overtime rate and population can change in HAM
    # after the period was created (e.g. HRD fills in an overtime rate), and the slips must follow
    ids, emp_meta = await sync_employees(payroll_month(period["start_date"]))
    q = {"id": {"$in": ids}}
    emps = await db.employees.find(q, {"_id": 0}).to_list(5000)
    by_rosy = {e["rosy_employee_id"]: e["id"] for e in emps if e.get("rosy_employee_id")}
    by_nik = {e["nik"]: e["id"] for e in emps}
    # every HAM read happens before anything of this period is deleted
    try:
        rows, meta = await integrations.fetch_attendance(period["start_date"], period["end_date"], emps)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data absensi dari RUMATKU: {e}")
    try:
        overtime = await integrations.fetch_overtime(payroll_month(period["start_date"]))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data lembur dari ROSY: {e}")
    # slip signer = ROSY's payroll Document Signer for this company (same as ROSY's own slips): name & position, printed
    # under the slip's QR code; its signature image is no longer used (user 14 Oct 2026)
    signer = emp_meta.get("penandatangan")
    await signer_mod.remember(signer, emp_meta.get("company"))
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "employee_ids": ids, "employee_count": len(ids), "employees_synced_at": now_iso(),
        "employees_source": integrations.mode("ROSY"), "employees_skipped": emp_meta.get("dilewati") or [],
        "company": emp_meta.get("company"), "signer": signer}})
    # draft slips of people who dropped out of the population (resigned, no salary contract) must not linger
    await db.payslips.delete_many({"payroll_period_id": pid, "employee_id": {"$nin": ids}, "status": {"$ne": "approved"}})
    # ROSY Tambahan Bulanan for this month: Transport Homecare, Bonus, THR, Potongan Tidak Mencapai Target, Cicilan
    component_ids = {kode: cid for cid, kode in integrations.MONTHLY_COMPONENTS.items()}
    comp_docs = [{"id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": by_rosy[rid], "kode": kode,
                  "component_id": component_ids[kode], "nominal": nominal, "synced_at": now_iso()}
                 for rid, comps in (emp_meta.get("components") or {}).items() if rid in by_rosy
                 for kode, nominal in comps.items()]
    transport_docs = [d for d in comp_docs if d["kode"] == "TRANSPORT_HOMECARE"]
    await db.period_components.delete_many({"payroll_period_id": pid})
    if comp_docs:
        await db.period_components.insert_many(comp_docs)
    await db.attendance_daily_logs.delete_many({"employee_id": {"$in": [e["id"] for e in emps]},
                                                "work_date": {"$gte": period["start_date"], "$lte": period["end_date"]}})
    # Approved overtime claims paid in this period (live only): the slip uses these, the daily log only shows them
    claim_docs, claim_minutes = [], {}
    if overtime is not None:
        claims, ot_meta = overtime
        for c in claims:
            eid = by_rosy.get(c["rosy_employee_id"])
            if not eid:
                continue
            claim_docs.append({**c, "id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": eid,
                               "synced_at": now_iso()})
            claim_minutes[(eid, c["tanggal"])] = claim_minutes.get((eid, c["tanggal"]), 0) + c["menit_disetujui"]
        await db.overtime_claims.delete_many({"payroll_period_id": pid})
        if claim_docs:
            await db.overtime_claims.insert_many(claim_docs)
    unknown, docs = set(), []
    for r in rows:
        key = r.pop("rosy_employee_id", None)
        nik = r.pop("nik", None)
        eid = by_rosy.get(key) if key else by_nik.get(nik)
        if not eid or not (period["start_date"] <= r["work_date"] <= period["end_date"]):
            unknown.add(key or nik)
            continue
        if (eid, r["work_date"]) in claim_minutes:
            r["overtime_hours"] = claim_minutes[(eid, r["work_date"])] / 60
        docs.append({**r, "id": str(uuid.uuid4()), "employee_id": eid, "source": "rumatku",
                     "synced_at": now_iso()})
    if docs:
        await db.attendance_daily_logs.insert_many(docs)
    if overtime is not None:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"overtime_source": "ham", "overtime_summary": {
            "periode_bayar": ot_meta.get("periode_bayar"), "claims": len(claim_docs),
            "employees": len({d["employee_id"] for d in claim_docs}),
            "minutes": sum(d["menit_disetujui"] for d in claim_docs), "pending": ot_meta.get("menunggu", 0),
            "without_rate": ot_meta.get("tanpa_tarif") or []}}})
    # Without attendance rows an employee keeps the full attendance allowance — report them, never drop silently
    unlinked = meta.get("unlinked") or []
    unlinked_ids = {u.get("employee_id") for u in unlinked}
    logged = {d["employee_id"] for d in docs}
    missing = [{"employee_id": e["id"], "nik": e["nik"], "name": e["name"]} for e in emps
               if e["id"] not in logged and not e.get("attendance_exempt")
               and e.get("rosy_employee_id") not in unlinked_ids]
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "attendance_synced_at": now_iso(), "attendance_count": len(docs),
        "attendance_source": integrations.mode("RUMATKU"), "attendance_unlinked": unlinked,
        "attendance_missing": missing, "attendance_unknown": sorted(unknown),
        "components_summary": {"transport_employees": len(transport_docs),
                               "transport_total": sum(d["nominal"] for d in transport_docs)}}})
    processed = await process_period(await get_period(pid))
    return {"logs": len(docs), "processed": processed, "unknown_niks": sorted(unknown),
            "unlinked": unlinked, "missing": missing, "transport_employees": len(transport_docs)}


@router.get("/periods/{pid}")
async def period_detail(pid: str):
    period = await get_period(pid)
    slips = await db.payslips.find({"payroll_period_id": pid}, {"_id": 0, "bpjs": 0}) \
        .sort("employee.nik", 1).to_list(2000)
    present = await _present_days(period, [s["employee_id"] for s in slips])
    dates = {e["id"]: e async for e in db.employees.find({"id": {"$in": [s["employee_id"] for s in slips]}},
                                                         {"_id": 0, "id": 1, "join_date": 1, "exit_date": 1})}
    # summary cards on top of the period, which also filter the table (user requests 10 Oct 2026): employee ids per card
    groups = {k: [] for k in ("overtime", "homecare", "unpaid", "maternity", "partial")}
    hours = overtime_pay = homecare = 0
    for s in slips:
        # slips calculated before Poin Absensi existed keep their alfa/izin days in the discipline breakdown
        disc = s.pop("discipline", None) or {}
        s.setdefault("absence_points", disc.get("basic_cut_days", 0))
        eid = s["employee_id"]
        if s.get("overtime_pay"):
            groups["overtime"].append(eid)
            hours += s.get("overtime_hours") or 0
            overtime_pay += s["overtime_pay"]
        if s.get("transport_homecare"):
            groups["homecare"].append(eid)
            homecare += s["transport_homecare"]
        if s.get("payroll_status") == "unpaid_leave":
            groups["unpaid"].append(eid)
            continue
        maternity = ((s.get("prorata") or {}).get("maternity_days")
                     or (disc.get("presence_by_type") or {}).get("maternity_leave", 0))
        if maternity:
            groups["maternity"].append(eid)
        if _prorata_note(s, dates.get(eid) or {}, period, maternity, present.get(eid, 0)):
            groups["partial"].append(eid)
    # accounts not payable through Batch Payment BSI block Lock & Approve (user 14 Oct 2026): the banner lists them,
    # the "Rekening Belum Siap" card filters the table to them
    blockers = await _account_blockers(slips)
    summary = {"included": len(slips), "overtime_hours": hours, "overtime_pay": overtime_pay, "homecare_total": homecare,
               **groups, "bank": [b["employee_id"] for b in blockers]}
    return {"period": period, "payslips": slips, "summary": summary, "bank_blockers": blockers,
            "signer_status": signer_mod.status(period.get("signer"))}


@router.delete("/periods/{pid}")
async def delete_period(pid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    manager = user["role"] == "manager_hrd"
    if period["status"] == "pending_approval" and not manager:
        raise HTTPException(403, "Periode yang sudah diajukan hanya dapat dihapus Manager HRD")
    if period["status"] not in EDITABLE_STATUSES + ("pending_approval",) or \
            await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Hanya periode yang belum memiliki slip approved yang dapat dihapus")
    res = await db.payslips.delete_many({"payroll_period_id": pid})
    await db.overtime_claims.delete_many({"payroll_period_id": pid})
    await db.period_components.delete_many({"payroll_period_id": pid})
    await db.payroll_periods.delete_one({"id": pid})
    return {"ok": True, "deleted_payslips": res.deleted_count}


EDITABLE_STATUSES = ("draft", "revision")


async def _log(pid: str, action: str, user: dict, reason: str = "", extra: Optional[dict] = None):
    entry = {"action": action, "by": actor(user), "by_name": user.get("name"), "at": now_iso(), "reason": reason}
    await db.payroll_periods.update_one({"id": pid}, {"$set": extra or {}, "$push": {"review_history": entry}})


class RejectIn(BaseModel):
    reason: str


@router.post("/periods/{pid}/process")
async def run_process(pid: str):
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci")
    count = await process_period(period)
    return {"processed": count}


@router.post("/periods/{pid}/submit")
async def submit_period(pid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Hanya periode draft / revisi yang dapat diajukan")
    if period.get("last_sync_error") or not period.get("attendance_synced_at"):
        raise HTTPException(400, "Sinkron dari ROSY belum berhasil. Klik \"Fetch Data Terbaru\" di halaman periode sebelum mengajukan")
    if not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    # the account gate of Lock & Approve already applies here (user 14 Oct 2026): a draft the Manager could not approve
    # is not handed over, and while it is a draft "Fetch Data Terbaru" can still bring the fixed accounts in
    blockers = await _account_blockers(await db.payslips.find(
        {"payroll_period_id": pid, "status": {"$ne": "approved"}}, SLIP_ACCOUNT_FIELDS).to_list(None))
    if blockers:
        raise _accounts_not_ready(blockers, "Belum bisa diajukan ke Manager")
    await _log(pid, "submitted", user, extra={"status": "pending_approval", "submitted_by": actor(user),
                                              "submitted_by_name": user.get("name"), "submitted_at": now_iso()})
    return await get_period(pid)


@router.post("/periods/{pid}/reject")
async def reject_period(pid: str, body: RejectIn, user: dict = Depends(require_manager)):
    period = await get_period(pid)
    reason = body.reason.strip()
    if len(reason) < 5:
        raise HTTPException(400, "Alasan penolakan wajib diisi (min. 5 karakter)")
    if period["status"] != "pending_approval":
        raise HTTPException(400, "Hanya periode yang menunggu approval yang dapat ditolak")
    if await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Sebagian slip sudah di-approve; tidak dapat ditolak")
    await _log(pid, "rejected", user, reason, {"status": "revision", "rejection_reason": reason,
                                               "rejected_by": actor(user), "rejected_by_name": user.get("name"),
                                               "rejected_at": now_iso()})
    return await get_period(pid)


def _ensure_synced(period: dict):
    """The gate submitting applies, for a Manager approving straight from draft."""
    if period.get("last_sync_error") or not period.get("attendance_synced_at"):
        raise HTTPException(400, "Sinkron dari ROSY belum berhasil. Klik \"Fetch Data Terbaru\" di halaman periode sebelum di-approve")


BANK_FIELDS = {"_id": 0, "id": 1, "nik": 1, "name": 1, "bank_code": 1, "bank_name": 1, "bank_account_number": 1,
               "bank_account_name": 1}
# what approval_blockers reads from a slip
SLIP_ACCOUNT_FIELDS = {"_id": 0, "employee_id": 1, "employee.nik": 1, "employee.name": 1, "status": 1,
                       "payroll_status": 1, "take_home_pay": 1}


async def _account_blockers(slips: list) -> list:
    """bank_batch.approval_blockers against the bank data the bank file reads: the employee master as last synced from
    ROSY, so an account fixed in ROSY HRD counts as soon as it is synced (also while the period is pending)."""
    emps = {e["id"]: e async for e in db.employees.find({"id": {"$in": [s["employee_id"] for s in slips]}}, BANK_FIELDS)}
    return approval_blockers(slips, emps)


def _accounts_not_ready(blockers: list, refused: str = "Lock & Approve diblokir") -> HTTPException:
    """User 14 Oct 2026: no account number, no account name or not BSI = the payroll cannot be processed — neither
    submitted to the Manager nor Lock & Approved."""
    kinds = Counter(p["kind"] for b in blockers for p in b["problems"])
    who = blockers[0]["name"] if len(blockers) == 1 else f"{len(blockers)} karyawan"
    return HTTPException(400, f"{refused}: rekening {who} belum siap dibayar lewat BSI "
                              f"({', '.join(f'{k} {n}' for k, n in kinds.most_common())}). "
                              "Lengkapi di ROSY HRD (Ubah Karyawan), lalu sinkron ulang dari ROSY")


@router.post("/periods/{pid}/approve-all")
async def approve_all(pid: str, user: dict = Depends(require_manager)):
    """Lock & Approve every slip. The Manager may do it straight from draft, without the Supervisor submitting first
    (user decision 10 Oct 2026)."""
    period = await get_period(pid)
    if period["status"] == "approved":
        raise HTTPException(400, "Periode sudah dikunci & di-approve")
    if not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    moved_from = period["status"] if period["status"] in EDITABLE_STATUSES else None
    if moved_from:
        _ensure_synced(period)
        # leave the editable states first, as submitting does, so neither a sync nor the Supervisor can change slips
        # while they are being locked one by one
        stale = (datetime.now(timezone.utc) - SYNC_STALE).isoformat()
        moved = await db.payroll_periods.update_one(
            {"id": pid, "status": {"$in": list(EDITABLE_STATUSES)},
             "$or": [{"sync_running_since": None}, {"sync_running_since": {"$exists": False}},
                     {"sync_running_since": {"$lt": stale}}]},
            {"$set": {"status": "pending_approval"}})
        if not moved.modified_count:
            raise HTTPException(409, "Periode sedang disinkron atau baru saja berubah. Muat ulang lalu coba lagi")
        period = await get_period(pid)
    # urut NIK: nomor dokumen slip (verify.py) yang terbit bersamaan ikut urutan NIK
    slips = await db.payslips.find({"payroll_period_id": pid, "status": {"$ne": "approved"}}, {"_id": 0}) \
        .sort("employee.nik", 1).to_list(2000)
    # every account must be payable through Batch Payment BSI before anything is locked (user 14 Oct 2026). Checked
    # once the period has left the editable states, so no sync can add a slip behind the check
    blockers = await _account_blockers(slips)
    if blockers:
        if moved_from:  # nothing locked: give the period back as it was
            await db.payroll_periods.update_one({"id": pid, "status": "pending_approval"}, {"$set": {"status": moved_from}})
        raise _accounts_not_ready(blockers)
    done = 0
    try:
        for s in slips:
            await approve_slip(s, period, user)
            done += 1
    except Exception:
        # nothing locked yet: give the period back as it was, instead of leaving a draft nobody submitted waiting
        # for approval (once a slip is locked it stays pending, and Lock & Approve finishes the rest)
        if moved_from and not done:
            await db.payroll_periods.update_one({"id": pid, "status": "pending_approval"}, {"$set": {"status": moved_from}})
        raise
    await _log(pid, "approved", user)
    return {"approved": len(slips)}


async def _slip(pid: str, eid: str) -> dict:
    s = await db.payslips.find_one({"payroll_period_id": pid, "employee_id": eid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Slip belum dihitung. Jalankan proses payroll")
    return s


@router.get("/periods/{pid}/employees/{eid}")
async def workbench(pid: str, eid: str):
    period = await get_period(pid)
    emp = await get_employee(eid)
    slip = await _slip(pid, eid)
    # slips calculated before 12 Oct carry no label yet: same rule as the PDF, from the slip's employee snapshot
    slip.setdefault("position_allowance_label", position_allowance_label(slip.get("employee") or emp))
    # why Lock & Approve of this slip is refused (user 14 Oct 2026); empty once approved or when nothing is transferred
    blockers = await _account_blockers([slip])
    return {"period": period, "employee": emp, "payslip": slip, "attendance": await period_logs(eid, period),
            "bank_problems": blockers[0]["problems"] if blockers else []}


@router.post("/periods/{pid}/employees/{eid}/preview")
async def preview(pid: str, eid: str, body: AdjustIn):
    period = await get_period(pid)
    emp = await get_employee(eid)
    return await build_slip(period, emp, body.model_dump())


@router.put("/periods/{pid}/employees/{eid}")
async def save_draft(pid: str, eid: str, body: AdjustIn, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    emp = await get_employee(eid)
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve & dikunci")
    if period["status"] not in EDITABLE_STATUSES and user["role"] != "manager_hrd":
        raise HTTPException(400, "Periode sedang direview Manager; tidak dapat diubah")
    adj = {k: getattr(body, k) for k in ADJ_KEYS}
    return await recalc_and_save(period, emp, adj, notes=body.adjustment_notes, manual=True)


@router.post("/periods/{pid}/employees/{eid}/approve")
async def approve_one(pid: str, eid: str, user: dict = Depends(require_manager)):
    period = await get_period(pid)
    if period["status"] in EDITABLE_STATUSES:  # straight from draft too (user 10 Oct 2026)
        _ensure_synced(period)
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve")
    blockers = await _account_blockers([slip])  # the same account rules as Lock & Approve of the whole period
    if blockers:
        raise _accounts_not_ready(blockers)
    return await approve_slip(slip, period, user)


async def _locked(pid: str) -> dict:
    period = await get_period(pid)
    if period["status"] != "approved":
        raise HTTPException(400, "Slip dikirim ke Rumatku setelah seluruh periode di-approve & dikunci")
    return period


@router.post("/periods/{pid}/resend-failed", dependencies=[Depends(require_manager)])
async def resend_failed(pid: str):
    await _locked(pid)
    n = await queue_delivery(pid, {"delivery_status": "failed"}, attempts=1)
    if not n:
        raise HTTPException(400, "Tidak ada slip gagal kirim")
    return {"queued": n}


@router.post("/periods/{pid}/employees/{eid}/resend", dependencies=[Depends(require_manager)])
async def resend_one(pid: str, eid: str):
    await _locked(pid)
    slip = await _slip(pid, eid)
    if slip.get("delivery_status") == "sent":
        raise HTTPException(400, "Slip sudah terkirim ke Rumatku")
    if slip.get("delivery_status") == "queued":
        raise HTTPException(400, "Slip sedang dikirim")
    return {"queued": await queue_delivery(pid, {"employee_id": eid}, attempts=1)}


@router.get("/periods/{pid}/employees/{eid}/pdf")
async def preview_pdf(pid: str, eid: str):
    period = await get_period(pid)
    # the preview carries the QR of the final slip (verify.with_preview): same code, address from the Konfigurasi
    slip = await verify.with_preview(await _slip(pid, eid), await get_configs())
    return Response(render_payslip(slip, period), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="preview-{slip["employee"]["nik"]}.pdf"'})
