"""Payroll period rules: one period per month (as in ROSY HAM, 1 slip per employee per month), auto name."""
from datetime import date

from fastapi import HTTPException

BULAN = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember")
MAX_DAYS = 31  # HAM presensi refuses longer ranges


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
