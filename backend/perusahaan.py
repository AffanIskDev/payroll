"""Identitas perusahaan (multi-PT, 6 Nov 2026).

Pembagian (keputusan user 6 Nov 2026):
  - IDENTITAS PT (nama legal, NPWP, alamat, logo, penandatangan) dipegang ROSY v2 — Master Perusahaan. RUSA hanya membaca:
    meta.company feed /karyawan (nama legal, NPWP, alamat) dan /perusahaan/logo, disimpan di koleksi global `companies`
    setiap Fetch Data Terbaru.
  - SETELAN PAYROLL per PT (UMK, plafon, dasar BPJS/PPh 21, rekening debet BSI, …) tetap di Konfigurasi RUSA.
COMPANY_NAME / COMPANY_NPWP / COMPANY_ADDRESS di Konfigurasi kini hanya cadangan bila ROSY masih kosong.

Kop slip: RUMAT (CP-001) tetap kop dua logo RPI + RUMAT (assets/); PT lain memakai logo PT dari ROSY (disimpan PNG di
storage/logos/<PT>.png); tanpa logo = nama legal sebagai teks."""
import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

import integrations
from core import current_company, db, get_configs, now_iso

logger = logging.getLogger("perusahaan")

LOGOS = Path(__file__).parent / "storage" / "logos"
LOGOS.mkdir(parents=True, exist_ok=True)
# PT yang kopnya dua logo tertanam (RPI = badan hukum, RUMAT = merek) — kop lama, tidak berubah
KOP_RPI_RUMAT = {"CP-001"}
# isian bawaan DEFAULT_CONFIGS yang berarti "belum diisi"
_KOSONG = ("", "-", "[NAMA_PERUSAHAAN]", "[ALAMAT_PERUSAHAAN]", "[NPWP_PEMOTONG]")


def _isi(v) -> Optional[str]:
    s = str(v or "").strip()
    return None if s in _KOSONG else s


def logo_path(company_id: str) -> Optional[Path]:
    p = LOGOS / f"{company_id}.png"
    return p if p.is_file() else None


def ke_png(isi: bytes) -> bytes:
    """Logo apa pun yang dibaca Pillow (PNG/JPG/WebP/GIF) → PNG RGBA, sisi terpanjang maks. 1200 px (cukup untuk kop A4)."""
    with PILImage.open(io.BytesIO(isi)) as im:
        im = im.convert("RGBA")
        im.thumbnail((1200, 1200))
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue()


async def simpan_identitas(company: Optional[dict]) -> None:
    """Identitas PT dari meta.company feed ROSY → koleksi `companies` (PT aktif). None (mode mock / feed lama) = tidak diubah."""
    if not company:
        return
    pt = current_company()
    if company.get("id") and company["id"] != pt:
        logger.warning("Identitas PT %s diabaikan: sesi sedang PT %s", company.get("id"), pt)
        return
    await db.companies.update_one({"id": pt}, {"$set": {"rosy": {
        "nama": company.get("nama"), "nama_legal": company.get("nama_legal"), "npwp": company.get("npwp"),
        "alamat": company.get("alamat"), "synced_at": now_iso()}}})


async def segarkan_logo() -> Optional[str]:
    """Unduh logo PT aktif dari ROSY bila sidiknya berubah. Gagal (ROSY mati, logo belum ada, format tak terbaca) TIDAK
    menggagalkan Fetch: kop memakai logo terakhir yang tersimpan, atau nama legal. Mengembalikan pesan masalah / None."""
    pt = current_company()
    doc = await db.companies.find_one({"id": pt}, {"_id": 0, "logo_versi": 1}) or {}
    try:
        hasil = await integrations.fetch_company_logo(doc.get("logo_versi") if logo_path(pt) else None)
    except Exception as e:  # noqa: BLE001
        logger.warning("Logo %s tidak terambil dari ROSY: %s", pt, e)
        return f"Logo belum terambil dari ROSY: {e}"
    if hasil is None:          # ROSY mock / sidik sama dengan yang tersimpan
        return None
    isi, versi = hasil
    if isi is None:
        await db.companies.update_one({"id": pt}, {"$set": {"logo_masalah": "Logo belum diatur di ROSY (Master Perusahaan)"}})
        return "Logo belum diatur di ROSY (Master Perusahaan)"
    try:
        png = ke_png(isi)
    except Exception as e:  # noqa: BLE001 — mis. SVG: Pillow tidak bisa membacanya
        msg = "Format logo di ROSY tidak bisa dipakai untuk slip (pakai PNG/JPG/WebP)"
        logger.warning("Logo %s: %s (%s)", pt, msg, e)
        await db.companies.update_one({"id": pt}, {"$set": {"logo_masalah": msg}})
        return msg
    (LOGOS / f"{pt}.png").write_bytes(png)
    await db.companies.update_one({"id": pt}, {"$set": {"logo_versi": versi, "logo_synced_at": now_iso()},
                                               "$unset": {"logo_masalah": ""}})
    return None


async def identitas(cfg: Optional[dict] = None) -> dict:
    """Identitas PT aktif untuk dokumen (1721-A1, kop): dari ROSY, cadangan Konfigurasi RUSA. `kosong` = yang belum ada."""
    pt = current_company()
    cfg = cfg if cfg is not None else await get_configs()
    doc = await db.companies.find_one({"id": pt}, {"_id": 0}) or {"id": pt}
    r = doc.get("rosy") or {}
    out = {
        "id": pt, "nama": r.get("nama") or doc.get("nama"),
        "nama_legal": _isi(r.get("nama_legal")) or _isi(cfg.get("COMPANY_NAME")) or doc.get("nama_legal") or doc.get("nama"),
        "npwp": _isi(r.get("npwp")) or _isi(cfg.get("COMPANY_NPWP")),
        "alamat": _isi(r.get("alamat")) or _isi(cfg.get("COMPANY_ADDRESS")),
        "sumber": {k: ("rosy" if _isi(r.get(k)) else "rusa") for k in ("nama_legal", "npwp", "alamat")},
        "rosy_synced_at": r.get("synced_at"), "logo": bool(logo_path(pt)), "kop_rpi_rumat": pt in KOP_RPI_RUMAT,
        "logo_synced_at": doc.get("logo_synced_at"), "logo_masalah": doc.get("logo_masalah"),
    }
    out["kosong"] = [k for k in ("npwp", "alamat") if not out[k]]
    if not out["logo"] and not out["kop_rpi_rumat"]:
        out["kosong"].append("logo")
    return out
