"""Verifikasi slip lewat QR (user 14 Okt 2026): "tanda tangan" slip = QR code per slip, bukan gambar tanda tangan.

Tiap slip punya `verify_code` yang tidak bisa ditebak; QR di slip berisi {alamat}/verifikasi/{kode}. Siapa pun yang
memindainya (karyawan, bank, pemilik kontrakan) membuka halaman publik RUSA yang mengonfirmasi bahwa slip itu pernah
di-approve HRD — tanpa nominal gaji, nama karyawan disamarkan. Alamat QR dibekukan di slip saat di-approve
(`verify_url`) supaya PDF yang dibuat ulang memuat QR yang sama; slip draft memakai alamat dari Konfigurasi yang
berlaku saat dirender, jadi Preview PDF Slip sama dengan slip akhirnya.

15 Okt 2026 (masukan user): slip yang di-approve juga mendapat nomor dokumen (`doc_number`, 'SG/RUMAT/2026/09/0001')
yang dicetak di slip bersama tanggal terbitnya, dan halaman verifikasi menyebut status penerbitan & persetujuan, nomor,
tanggal terbit, serta waktu pemeriksaan — supaya isi slip di tangan bisa dicocokkan dengan catatan sistem."""
import os
import re
import secrets
from typing import Optional
from urllib.parse import urlparse

from pymongo import ReturnDocument

from core import db, now_iso

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{10,40}$")
PATH = "/verifikasi"  # halaman publik di frontend: /verifikasi/:kode
_PRIVATE_HOST = re.compile(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")


def new_code() -> str:
    """12 karakter (72 bit) acak yang aman di URL: cukup pendek untuk QR kecil, terlalu panjang untuk ditebak."""
    return secrets.token_urlsafe(9)


def clean_base(url: Optional[str]) -> str:
    """Alamat web yang layak dipakai tanpa garis miring penutup, atau ''."""
    url = (url or "").strip().rstrip("/")
    parts = urlparse(url)
    return url if parts.scheme in ("http", "https") and parts.netloc and not any(c.isspace() for c in url) else ""


def base_url(cfg: Optional[dict]) -> str:
    """Konfigurasi SLIP_VERIFY_BASE_URL; kosong → alamat frontend pertama di CORS_ORIGINS (halaman verifikasi ada di
    frontend yang sama dengan RUSA)."""
    own = clean_base((cfg or {}).get("SLIP_VERIFY_BASE_URL"))
    if own:
        return own
    for origin in os.environ.get("CORS_ORIGINS", "").split(","):
        if clean_base(origin):
            return clean_base(origin)
    return ""


def is_local(base: str) -> bool:
    """Alamat yang hanya terbuka di komputer/jaringan ini: QR-nya tidak bisa dipindai dari HP karyawan di luar."""
    host = (urlparse(base).hostname or "").lower()
    return host in ("localhost", "::1") or bool(_PRIVATE_HOST.match(host))


def url_for(code: str, cfg: Optional[dict]) -> str:
    base = base_url(cfg)
    return f"{base}{PATH}/{code}" if base and code else ""


def mask_name(name: Optional[str]) -> str:
    """'Sri Wahyuni Putri' → 'Sri W. P.': nama depan utuh, sisanya inisial — cukup untuk pemegang slip mengenalinya, tidak
    cukup untuk orang asing. Nama satu kata tampil utuh seperti nama depan lainnya (15 Okt 2026: 'N***' untuk 'Noviyanto'
    tidak bisa dicocokkan dengan slip)."""
    parts = (name or "").split()
    if not parts:
        return "-"
    return " ".join([parts[0]] + [p[0].upper() + "." for p in parts[1:]])


def company_code(period: dict) -> str:
    """'RUMAT': nama singkat perusahaan periode (dari ROSY); 'RUSA' bila periode tidak menyebut perusahaan."""
    company = period.get("company") or {}
    return re.sub(r"[^A-Z0-9]", "", (company.get("nama") or company.get("id") or "").upper()) or "RUSA"


def doc_number(period: dict, seq: int) -> str:
    """'SG/RUMAT/2026/09/0001': Slip Gaji, perusahaan, bulan gaji, urutan terbit di periode itu."""
    month = period.get("bulan") or (period.get("start_date") or "")[:7]
    return f"SG/{company_code(period)}/{month.replace('-', '/')}/{seq:04d}"


async def next_doc_number(period: dict) -> str:
    """Nomor berikutnya di periode ini. $inc atomik: dua approve yang berjalan bersamaan tidak mendapat nomor yang sama."""
    p = await db.payroll_periods.find_one_and_update({"id": period["id"]}, {"$inc": {"doc_seq": 1}},
                                                     projection={"_id": 0, "doc_seq": 1},
                                                     return_document=ReturnDocument.AFTER)
    return doc_number(period, p["doc_seq"])


async def stamp(slip: dict, period: dict, cfg: Optional[dict]) -> dict:
    """Yang dibekukan saat sebuah slip di-approve: kode, alamat yang tercetak di QR, nomor dokumen, dan penandatangan yang
    disebut di halaman verifikasi (periode bisa berganti penandatangan sesudahnya)."""
    code = slip.get("verify_code") or new_code()
    signer = period.get("signer") or {}
    return {"verify_code": code, "verify_url": url_for(code, cfg),
            "doc_number": slip.get("doc_number") or await next_doc_number(period),
            "verify_signer": {"nama": signer.get("nama"), "jabatan": signer.get("jabatan")}}


async def with_preview(slip: dict, cfg: Optional[dict]) -> dict:
    """Slip seperti yang dicetak Preview PDF: slip approved persis seperti saat di-approve; draft mendapat kodenya
    (disimpan saat pertama dipakai, jadi QR di preview = QR slip akhirnya) dan alamat yang sedang dikonfigurasi."""
    if slip.get("status") == "approved":
        return slip
    code = slip.get("verify_code")
    if not code:
        await db.payslips.update_one({"id": slip["id"], "verify_code": {"$exists": False}},
                                     {"$set": {"verify_code": new_code()}})
        code = ((await db.payslips.find_one({"id": slip["id"]}, {"_id": 0, "verify_code": 1})) or {}).get("verify_code")
    return {**slip, "verify_code": code, "verify_url": url_for(code or "", cfg)}


async def lookup(code: str) -> Optional[dict]:
    """Jawaban publik untuk kode yang dipindai, atau None bila kode tidak dikenal/tidak wajar (pemanggil menjawab 404).
    Semuanya dibaca dari slip di database saat itu juga (`diperiksa_pada`), tidak ada yang diambil dari alamat QR: kode
    yang diubah satu huruf pun tidak dikenal, dan slip yang belum di-approve tidak pernah tampil sah. Slip draft tidak
    membuka apa pun selain statusnya."""
    if not CODE_RE.match(code or ""):
        return None
    slip = await db.payslips.find_one({"verify_code": code}, {
        "_id": 0, "status": 1, "approved_at": 1, "payroll_period_id": 1, "employee.name": 1, "verify_signer": 1,
        "doc_number": 1})
    if not slip:
        return None
    checked = now_iso()
    if slip.get("status") != "approved":
        return {"status": "belum_disetujui", "status_penerbitan": "belum_diterbitkan", "status_persetujuan": "menunggu",
                "kode": code, "diperiksa_pada": checked}
    period = await db.payroll_periods.find_one({"id": slip["payroll_period_id"]},
                                               {"_id": 0, "period_name": 1, "company": 1, "signer": 1}) or {}
    signer = slip.get("verify_signer") or period.get("signer") or {}
    company = period.get("company") or {}
    # slip yang di-approve sebelum 15 Okt 2026 belum punya nomor dokumen: id_dokumen None, halaman tidak menampilkannya
    return {"status": "sah", "dokumen": "Slip Gaji", "id_dokumen": slip.get("doc_number"),
            "diterbitkan_pada": slip.get("approved_at"), "status_penerbitan": "diterbitkan",
            "status_persetujuan": "disetujui", "perusahaan": company.get("nama_legal") or company.get("nama"),
            "periode": period.get("period_name"), "karyawan": mask_name((slip.get("employee") or {}).get("name")),
            "penandatangan": {"nama": signer.get("nama"), "jabatan": signer.get("jabatan")},
            "kode": code, "diperiksa_pada": checked}
