"""Payroll period rules: one period per month (as in ROSY HAM, 1 slip per employee per month), auto name."""
from datetime import date

from fastapi import HTTPException

BULAN = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember")
MAX_DAYS = 31  # HAM presensi refuses longer ranges

# Jenis run (user 30 Okt 2026): gaji = siklus bulanan seperti biasa; THR & Bonus Tahunan = run sendiri yang dibayar di
# tanggal berbeda. Periode lama tanpa field run_type = gaji.
RUN_GAJI = "gaji"
RUN_SPECIAL = ("thr", "bonus_tahunan")
RUN_TYPES = (RUN_GAJI, *RUN_SPECIAL)
# THR dibaca run khusus mulai bulan ini; periode gaji sebelumnya tetap membawa THR di slipnya seperti saat diterbitkan
THR_RUN_FROM = "2026-11"


def run_type_of(doc: dict) -> str:
    return (doc or {}).get("run_type") or RUN_GAJI


def is_special(doc: dict) -> bool:
    return run_type_of(doc) in RUN_SPECIAL


def payroll_month(start: str) -> str:
    """The month a period belongs to — the same key used for HAM's employee, overtime and component feeds."""
    return start[:7]


def period_name_for(start: str, end: str) -> str | None:
    """'Oktober 2026' when the period lies within one month; cross-month periods need a typed name."""
    if start[:7] != end[:7]:
        return None
    return f"{BULAN[int(start[5:7]) - 1]} {start[:4]}"


def validate_dates(start: str, end: str) -> None:
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Format tanggal harus YYYY-MM-DD")
    if e < s:
        raise HTTPException(400, "Tanggal selesai tidak boleh sebelum tanggal mulai")
    if (e - s).days + 1 > MAX_DAYS:
        raise HTTPException(400, f"Periode maksimal {MAX_DAYS} hari")


def overlaps(start: str, end: str, other: dict) -> bool:
    return start <= other["end_date"] and other["start_date"] <= end
