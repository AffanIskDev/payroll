"""Tambahan Bulanan diinput di RUSA (user 18 Nov 2026, lanjutan gaji_rusa.py) untuk PT dengan Sumber Gaji = RUSA.

Di ROSY, Tambahan Bulanan (Bonus, Transport Rumat Kita, Potongan Tidak Mencapai Target, Cicilan / Pinjaman) diisi per bulan
dan RUSA membacanya saat Fetch ke `period_components`. Untuk PT bersumber RUSA nilai itu diisi di sini, per periode gaji,
dengan kode komponen yang SAMA sehingga engine menghitungnya persis seperti nilai dari ROSY (rumus tidak berubah).
Satu PT satu sumber: di mode RUSA, Tambahan Bulanan ROSY tidak dipakai (routes_hr.sync_employees mengosongkannya).

Disimpan per BULAN (bukan per id periode) di koleksi `komponen_bulanan`, kunci (bulan, rosy_employee_id, kode), supaya
tetap ada bila periodenya dihapus lalu dibuat ulang; perubahan dicatat di `komponen_bulanan_riwayat`. Menyimpan langsung
menghitung ulang slip draft karyawan yang berubah — tidak perlu Fetch. THR & Bonus Tahunan punya run sendiri (input RUSA
sudah ada di special_runs.py), jadi tidak ada di sini."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, actor, now_iso, require_hr
import gaji_rusa
from periods import payroll_month, run_type_of, RUN_GAJI
from pipeline import ADJ_KEYS, get_period, recalc_and_save, recompute_final_tax_periods

# kode period_components → (label, jenis, keterangan); urutan = urutan kolom di layar
KODE = {
    "BONUS": ("Bonus", "pendapatan", "Masuk pendapatan & dasar PPh 21, tidak masuk upah BPJS"),
    "TRANSPORT_HOMECARE": ("Transport Homecare", "pendapatan",
                           "Dianggap sudah dibayar di muka: masuk pendapatan & PPh 21, tetapi tidak ikut ditransfer (THP)"),
    "TARGET_DEDUCTION": ("Potongan Tidak Mencapai Target", "potongan", "Mengurangi THP, tidak mengurangi dasar PPh 21"),
    "LOAN_INSTALLMENT": ("Cicilan / Pinjaman", "potongan", "Mengurangi THP, tidak mengurangi dasar PPh 21"),
}
EDITABLE = ("draft", "revision")
MAKS = 1_000_000_000

router = APIRouter(prefix="/api/hr/tambahan-bulanan", dependencies=[Depends(require_hr)])


async def docs_periode(period: dict, by_rosy: dict) -> list:
    """period_components periode gaji ini dari input RUSA (mode RUSA), dipanggil routes_hr._sync saat Fetch."""
    bulan = period.get("bulan") or payroll_month(period["start_date"])
    return [{"id": str(uuid.uuid4()), "payroll_period_id": period["id"], "employee_id": by_rosy[d["rosy_employee_id"]],
             "kode": d["kode"], "nominal": float(d["nominal"]), "source": "rusa", "synced_at": now_iso()}
            async for d in db.komponen_bulanan.find({"bulan": bulan, "kode": {"$in": list(KODE)}}, {"_id": 0})
            if d["rosy_employee_id"] in by_rosy and float(d["nominal"]) > 0]


async def _periode_gaji(pid: str) -> dict:
    period = await get_period(pid)
    if run_type_of(period) != RUN_GAJI:
        raise HTTPException(400, "Tambahan Bulanan hanya untuk periode gaji (THR & Bonus Tahunan diisi di run-nya sendiri)")
    return period


@router.get("/{pid}")
async def daftar(pid: str):
    period = await _periode_gaji(pid)
    sumber = await gaji_rusa.sumber()
    bulan = period["bulan"]
    emps = await db.employees.find({"id": {"$in": period.get("employee_ids") or []}},
                                   {"_id": 0, "id": 1, "rosy_employee_id": 1, "nik": 1, "name": 1, "department": 1,
                                    "position": 1}).sort("name", 1).to_list(5000)
    nilai = {}
    async for d in db.komponen_bulanan.find({"bulan": bulan}, {"_id": 0}):
        nilai.setdefault(d["rosy_employee_id"], {})[d["kode"]] = d["nominal"]
    rows = [{**e, "nilai": {k: nilai.get(e.get("rosy_employee_id"), {}).get(k, 0) for k in KODE}} for e in emps]
    total = {k: sum(r["nilai"][k] for r in rows) for k in KODE}
    return {"period": {k: period.get(k) for k in ("id", "period_name", "bulan", "status")}, "sumber": sumber,
            "bisa_ubah": sumber == "rusa" and period["status"] in EDITABLE,
            "kode": [{"kode": k, "label": v[0], "jenis": v[1], "keterangan": v[2]} for k, v in KODE.items()],
            "rows": rows, "total": total}


class ItemIn(BaseModel):
    employee_id: str
    kode: str
    nominal: float = Field(ge=0, le=MAKS)


class SimpanIn(BaseModel):
    items: List[ItemIn]
    catatan: str = ""


@router.put("/{pid}")
async def simpan(pid: str, body: SimpanIn, user: dict = Depends(require_hr)):
    """Simpan beberapa nilai sekaligus (nominal 0 = hapus), lalu hitung ulang slip draft karyawan yang berubah."""
    period = await _periode_gaji(pid)
    if await gaji_rusa.sumber() != "rusa":
        raise HTTPException(409, "Tambahan Bulanan PT ini diambil dari ROSY. Ubah Sumber Gaji ke RUSA di Konfigurasi untuk "
                                 "mengisinya di RUSA")
    if period["status"] not in EDITABLE:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci; Tambahan Bulanan tidak dapat diubah")
    ids = set(period.get("employee_ids") or [])
    emps = {e["id"]: e async for e in db.employees.find({"id": {"$in": list({i.employee_id for i in body.items})}}, {"_id": 0})}
    for i in body.items:
        if i.kode not in KODE:
            raise HTTPException(400, f"Komponen tidak dikenal: {i.kode}")
        if i.employee_id not in ids or i.employee_id not in emps:
            raise HTTPException(400, "Karyawan tidak ada di periode ini — Fetch Data Terbaru dulu bila baru diisi gajinya")
    bulan, at, oleh = period["bulan"], now_iso(), actor(user)
    berubah = set()
    for i in body.items:
        e = emps[i.employee_id]
        kunci = {"bulan": bulan, "rosy_employee_id": e["rosy_employee_id"], "kode": i.kode}
        lama = await db.komponen_bulanan.find_one(kunci, {"_id": 0, "nominal": 1})
        sebelum = float(lama["nominal"]) if lama else 0.0
        baru = float(round(i.nominal))
        if sebelum == baru:
            continue
        if baru:
            await db.komponen_bulanan.update_one(kunci, {"$set": {**kunci, "nominal": baru, "updated_at": at, "updated_by": oleh},
                                                         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": at}}, upsert=True)
        else:
            await db.komponen_bulanan.delete_one(kunci)
        await db.komponen_bulanan_riwayat.insert_one({
            "id": str(uuid.uuid4()), **kunci, "employee_id": e["id"], "nik": e.get("nik"), "name": e.get("name"),
            "sebelum": sebelum, "sesudah": baru, "oleh": oleh, "at": at, "catatan": body.catatan.strip(),
            "payroll_period_id": pid})
        berubah.add(e["id"])
    # slip draft karyawan yang berubah dihitung ulang dari period_components yang baru (sama seperti sesudah Fetch)
    for eid in berubah:
        e = emps[eid]
        await db.period_components.delete_many({"payroll_period_id": pid, "employee_id": eid})
        docs = [{"id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": eid, "kode": d["kode"],
                 "nominal": float(d["nominal"]), "source": "rusa", "synced_at": at}
                async for d in db.komponen_bulanan.find({"bulan": bulan, "rosy_employee_id": e["rosy_employee_id"],
                                                         "kode": {"$in": list(KODE)}}, {"_id": 0})]
        if docs:
            await db.period_components.insert_many(docs)
        slip = await db.payslips.find_one({"payroll_period_id": pid, "employee_id": eid}, {"_id": 0})
        if slip and slip.get("status") != "approved":
            await recalc_and_save(period, e, {k: slip.get(k, 0) for k in ADJ_KEYS})
    # PPh 21 Pasal 17 (Desember / bulan keluar) di bulan ini atau sesudahnya ikut bila pendapatannya berubah
    recomputed = await recompute_final_tax_periods(bulan) if berubah else []
    return {"diubah": len(berubah), "recomputed": recomputed, **await daftar(pid)}


@router.get("/{pid}/riwayat")
async def riwayat(pid: str):
    period = await _periode_gaji(pid)
    return await db.komponen_bulanan_riwayat.find({"bulan": period["bulan"]}, {"_id": 0, "company_id": 0}) \
        .sort("at", -1).to_list(500)
