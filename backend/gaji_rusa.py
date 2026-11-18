"""Gaji karyawan diinput di RUSA (user 18 Nov 2026: "untuk RUMI, RKM atau Botanova tidak perlu input via ROSY tapi dari RUSA
juga bisa").

Per PT, Konfigurasi GAJI_SUMBER memilih SATU sumber gaji:
- `rosy` (bawaan, RUMAT): gaji dari Kontrak Gaji ROSY seperti selama ini — modul ini tidak melakukan apa-apa.
- `rusa`: identitas karyawan (nama, NIK, PTKP, rekening, tanggal masuk/keluar, akun RUMATKU) TETAP dari ROSY, tetapi gaji
  pokok, tunjangan jabatan, tunjangan kehadiran, tarif lembur dan program BPJS diisi di RUSA (menu Karyawan). Kontrak Gaji
  ROSY tidak dipakai (tidak ada "cadangan" diam-diam ke ROSY: satu PT, satu sumber); nilainya hanya disimpan sebagai
  `gaji_rosy` untuk tombol "Salin dari ROSY". Karyawan yang gajinya belum diisi tidak ikut periode (seperti karyawan tanpa
  Kontrak Gaji di ROSY) dan dilaporkan di meta.dilewati.

Gaji RUSA disimpan per PT di koleksi `gaji_karyawan` (kunci rosy_employee_id — tetap walau dokumen employees dibuat ulang),
setiap perubahan dicatat di `gaji_karyawan_riwayat`. Perubahan berlaku untuk slip draft sesudah Fetch Data Terbaru, sama
seperti perubahan Kontrak Gaji di ROSY."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, actor, get_configs, now_iso, require_hr, require_manager

KEY = "GAJI_SUMBER"
NOMINAL = ("basic_salary", "position_allowance", "monthly_attendance_allowance", "overtime_hourly_rate")
PROGRAMS = ("kes", "jkk", "jkm", "jht", "jp")
# Kelas risiko JKK (PP 44/2015): 0,24% / 0,54% / 0,89% / 1,27% / 1,74% upah
JKK_RATES = (0.0024, 0.0054, 0.0089, 0.0127, 0.0174)
# masalah data yang dihitung ROSY dari gajinya sendiri — di mode RUSA dihitung ulang dari gaji RUSA
ISSUES_GAJI = ("gaji_pokok_nol", "lembur_tanpa_tarif")
ALASAN_BELUM = "gaji belum diisi di RUSA"

router = APIRouter(prefix="/api/hr/gaji-karyawan", dependencies=[Depends(require_hr)])


async def sumber() -> str:
    return "rusa" if (await get_configs()).get(KEY, "rosy") == "rusa" else "rosy"


def gaji_dari_rosy(r: dict) -> Optional[dict]:
    """Nilai Kontrak Gaji ROSY pada baris hasil normalize_employee, atau None bila karyawan itu tak punya Kontrak Gaji."""
    if r.get("punya_kontrak_rosy") is False:
        return None
    return {**{k: float(r.get(k) or 0) for k in NOMINAL},
            "bpjs_programs": {p: bool((r.get("bpjs_programs") or {}).get(p)) for p in PROGRAMS},
            "jkk_rate": float(r.get("jkk_rate") or JKK_RATES[0])}


def terapkan(r: dict, gaji: dict) -> dict:
    """Baris karyawan dengan gaji RUSA menggantikan gaji ROSY; masalah data yang bergantung pada gaji dihitung ulang."""
    prog = {p: bool((gaji.get("bpjs_programs") or {}).get(p)) for p in PROGRAMS}
    out = {**r, **{k: float(gaji.get(k) or 0) for k in NOMINAL}, "bpjs_programs": prog, "has_bpjs_kes": prog["kes"],
           "has_bpjs_tk": any(prog[p] for p in ("jkk", "jkm", "jht", "jp")),
           "jkk_rate": float(gaji.get("jkk_rate") or JKK_RATES[0])}
    issues = [i for i in r.get("data_issues") or [] if i not in ISSUES_GAJI]
    if out["basic_salary"] <= 0:
        issues.append("gaji_pokok_nol")
    if out.get("overtime_access") and out["overtime_hourly_rate"] <= 0:
        issues.append("lembur_tanpa_tarif")
    out["data_issues"] = issues
    return out


async def gabungkan(rows: list) -> tuple:
    """Mode RUSA: (rows, dilewati). Setiap baris ROSY diberi gaji RUSA-nya; yang belum punya ditandai gaji_ada=False (tetap
    disimpan supaya tampil di menu Karyawan untuk diisi, tetapi tidak ikut periode)."""
    simpan = {g["rosy_employee_id"]: g async for g in db.gaji_karyawan.find(
        {"rosy_employee_id": {"$in": [r["rosy_employee_id"] for r in rows]}}, {"_id": 0})}
    out, dilewati = [], []
    for r in rows:
        ref = gaji_dari_rosy(r)
        g = simpan.get(r["rosy_employee_id"])
        base = {**r, "gaji_sumber": "rusa", "gaji_rosy": ref}
        if g:
            out.append({**terapkan(base, g), "gaji_ada": True, "gaji_diubah_at": g.get("updated_at"),
                        "gaji_diubah_oleh": g.get("updated_by")})
        else:
            # gaji kosong, bukan gaji ROSY: tidak ada yang terbayar dari sumber lain
            out.append({**terapkan(base, {}), "gaji_ada": False, "gaji_diubah_at": None, "gaji_diubah_oleh": None})
            dilewati.append({"employee_id": r["rosy_employee_id"], "nik": r["nik"], "name": r["name"], "alasan": ALASAN_BELUM})
    return out, dilewati


# ------------------------------------------------------------------ API

class GajiIn(BaseModel):
    basic_salary: float = Field(ge=0)
    position_allowance: float = Field(0, ge=0)
    monthly_attendance_allowance: float = Field(0, ge=0)
    overtime_hourly_rate: float = Field(0, ge=0)
    bpjs_programs: dict = {}
    jkk_rate: float = JKK_RATES[0]
    catatan: str = ""


def _bersih(body: GajiIn) -> dict:
    if body.basic_salary <= 0:
        raise HTTPException(400, "Gaji pokok wajib diisi (lebih dari Rp 0)")
    rate = round(float(body.jkk_rate), 4)
    if rate not in JKK_RATES:
        raise HTTPException(400, "Tarif JKK harus salah satu kelas risiko: 0,24%, 0,54%, 0,89%, 1,27% atau 1,74%")
    unknown = set(body.bpjs_programs) - set(PROGRAMS)
    if unknown:
        raise HTTPException(400, f"Program BPJS tidak dikenal: {', '.join(sorted(unknown))}")
    return {**{k: float(round(getattr(body, k))) for k in NOMINAL},
            "bpjs_programs": {p: bool(body.bpjs_programs.get(p)) for p in PROGRAMS}, "jkk_rate": rate}


async def _wajib_mode_rusa():
    if await sumber() != "rusa":
        raise HTTPException(409, "Gaji PT ini diambil dari Kontrak Gaji ROSY. Ubah Sumber Gaji ke RUSA di Konfigurasi "
                                 "(Manager HRD) untuk mengisi gaji di RUSA")


async def _karyawan(eid: str) -> dict:
    e = await db.employees.find_one({"id": eid}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Karyawan tidak ditemukan")
    if not e.get("rosy_employee_id"):
        raise HTTPException(400, "Karyawan ini tidak berasal dari ROSY")
    return e


async def simpan_gaji(e: dict, nilai: dict, oleh: str, catatan: str = "", sumber_ubah: str = "form") -> dict:
    """Simpan gaji RUSA satu karyawan + riwayat, dan perbarui dokumen employees supaya menu Karyawan langsung benar."""
    lama = await db.gaji_karyawan.find_one({"rosy_employee_id": e["rosy_employee_id"]}, {"_id": 0})
    sebelum = {k: lama.get(k) for k in (*NOMINAL, "bpjs_programs", "jkk_rate")} if lama else None
    at = now_iso()
    await db.gaji_karyawan.update_one(
        {"rosy_employee_id": e["rosy_employee_id"]},
        {"$set": {**nilai, "rosy_employee_id": e["rosy_employee_id"], "updated_at": at, "updated_by": oleh},
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": at}}, upsert=True)
    if sebelum != nilai:
        await db.gaji_karyawan_riwayat.insert_one({
            "id": str(uuid.uuid4()), "rosy_employee_id": e["rosy_employee_id"], "employee_id": e["id"], "nik": e.get("nik"),
            "name": e.get("name"), "sebelum": sebelum, "sesudah": nilai, "oleh": oleh, "at": at, "catatan": catatan.strip(),
            "sumber": sumber_ubah})
    baru = {**terapkan(e, nilai), "gaji_sumber": "rusa", "gaji_ada": True, "gaji_diubah_at": at, "gaji_diubah_oleh": oleh}
    baru.pop("company_id", None)
    await db.employees.update_one({"id": e["id"]}, {"$set": baru})
    return baru


@router.get("/info")
async def info():
    """Sumber gaji PT aktif untuk menu Karyawan, dan berapa karyawan yang gajinya belum diisi."""
    s = await sumber()
    out = {"sumber": s}
    if s == "rusa":
        out["belum"] = await db.employees.count_documents({"gaji_sumber": "rusa", "gaji_ada": False, "in_rosy": {"$ne": False}})
        out["bisa_salin"] = await db.employees.count_documents(
            {"gaji_sumber": "rusa", "gaji_ada": False, "gaji_rosy": {"$type": "object"}, "in_rosy": {"$ne": False}})
    return out


@router.get("/{eid}")
async def detail(eid: str):
    e = await _karyawan(eid)
    g = await db.gaji_karyawan.find_one({"rosy_employee_id": e["rosy_employee_id"]}, {"_id": 0, "company_id": 0})
    riwayat = await db.gaji_karyawan_riwayat.find({"rosy_employee_id": e["rosy_employee_id"]},
                                                  {"_id": 0, "company_id": 0}).sort("at", -1).to_list(50)
    return {"sumber": await sumber(), "gaji": g, "gaji_rosy": e.get("gaji_rosy"), "riwayat": riwayat,
            "jkk_rates": list(JKK_RATES)}


@router.put("/{eid}")
async def ubah(eid: str, body: GajiIn, user: dict = Depends(require_hr)):
    await _wajib_mode_rusa()
    e = await _karyawan(eid)
    return await simpan_gaji(e, _bersih(body), actor(user), body.catatan)


@router.post("/salin-dari-rosy", dependencies=[Depends(require_manager)])
async def salin_semua(user: dict = Depends(require_hr)):
    """Saat PT pindah ke sumber RUSA: gaji karyawan yang BELUM diisi di RUSA diisi dengan nilai Kontrak Gaji ROSY terakhir
    (hasil Fetch), supaya tidak ada yang hilang dari periode. Yang sudah diisi di RUSA tidak disentuh."""
    await _wajib_mode_rusa()
    n = 0
    async for e in db.employees.find({"gaji_sumber": "rusa", "gaji_ada": False, "gaji_rosy": {"$type": "object"}},
                                     {"_id": 0}):
        g = e["gaji_rosy"]
        if float(g.get("basic_salary") or 0) <= 0:
            continue
        rate = round(float(g.get("jkk_rate") or JKK_RATES[0]), 4)
        nilai = {**{k: float(g.get(k) or 0) for k in NOMINAL},
                 "bpjs_programs": {p: bool((g.get("bpjs_programs") or {}).get(p)) for p in PROGRAMS},
                 "jkk_rate": rate if rate in JKK_RATES else JKK_RATES[0]}
        await simpan_gaji(e, nilai, actor(user), "disalin dari Kontrak Gaji ROSY", "salin_rosy")
        n += 1
    return {"disalin": n, **await info()}
