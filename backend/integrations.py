"""Adapters for ROSY (employee & salary master) and RUMATKU (attendance, shift, overtime).
Live mode when ROSY_API_URL / RUMATKU_API_URL are set, otherwise MOCK (simulated JSON)."""
import hashlib
import os
from datetime import date, timedelta

import httpx

from seed import EMPLOYEES, BUDI_MARCH

LEAVE_TYPES = {"present", "sick_with_certificate", "annual_leave", "statutory_leave", "maternity_leave",
               "menstrual_leave", "approved_unpaid_leave", "alpha", "day_off"}


def mode(system: str) -> str:
    return "live" if os.environ.get(f"{system}_API_URL") else "mock"


async def _get(system: str, path: str, params: dict = None) -> list:
    url = os.environ[f"{system}_API_URL"].rstrip("/") + path
    headers = {"Authorization": f"Bearer {os.environ.get(f'{system}_API_KEY', '')}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url, headers=headers, params=params)
        r.raise_for_status()
        body = r.json()
    return body["data"] if isinstance(body, dict) else body


def _mock_rosy() -> list:
    return [{
        "nik": e["nik"], "name": e["name"], "email": e["email"], "department": e["department"],
        "birth_date": e["birth_date"], "gender": e["gender"], "marital_status": e["marital_status"],
        "dependents_count": e["dependents_count"], "has_husband_certificate": e["has_husband_certificate"],
        "npwp": "", "payroll_status": e["payroll_status"], "prolonged_illness_month_count": 0,
        "salary": {"basic_salary": e["basic_salary"], "position_allowance": e["position_allowance"],
                   "monthly_attendance_allowance": e["monthly_attendance_allowance"],
                   "overtime_hourly_rate": e["overtime_hourly_rate"]},
        "bpjs": {"has_bpjs_kes": True, "has_bpjs_tk": True, "jkk_rate": 0.0024},
        "bank": {"name": e["bank_name"], "account_number": e["bank_account_number"]},
    } for e in EMPLOYEES]


def normalize_employee(r: dict) -> dict:
    sal, bp, bank = r.get("salary") or {}, r.get("bpjs") or {}, r.get("bank") or {}
    return {
        "nik": str(r["nik"]).strip(), "name": r["name"], "email": (r.get("email") or "").lower(),
        "department": r.get("department") or "", "birth_date": r["birth_date"], "gender": r.get("gender", "L"),
        "marital_status": r.get("marital_status", "TK"), "dependents_count": int(r.get("dependents_count") or 0),
        "has_husband_certificate": bool(r.get("has_husband_certificate")), "npwp": r.get("npwp") or "",
        "payroll_status": r.get("payroll_status") or "active",
        "prolonged_illness_month_count": int(r.get("prolonged_illness_month_count") or 0),
        "basic_salary": float(sal.get("basic_salary") or 0), "position_allowance": float(sal.get("position_allowance") or 0),
        "monthly_attendance_allowance": float(sal.get("monthly_attendance_allowance") or 0),
        "overtime_hourly_rate": float(sal.get("overtime_hourly_rate") or 0),
        "has_bpjs_kes": bp.get("has_bpjs_kes", True), "has_bpjs_tk": bp.get("has_bpjs_tk", True),
        "jkk_rate": float(bp.get("jkk_rate") or 0.0024),
        "bank_name": bank.get("name") or "BSI", "bank_account_number": bank.get("account_number") or "",
    }


async def fetch_employees() -> list:
    raw = await _get("ROSY", "/employees") if mode("ROSY") == "live" else _mock_rosy()
    return [normalize_employee(r) for r in raw]


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _mock_day(nik: str, d: date, status: str) -> dict:
    base = {"nik": nik, "work_date": d.isoformat(), "overtime_hours": 0, "is_missing_check_in": False,
            "is_missing_check_out": False, "photo_in_url": None, "location_in": None}
    if status == "unpaid_leave":
        return {**base, "leave_type": "approved_unpaid_leave"}
    if d.weekday() == 6:
        return {**base, "leave_type": "day_off"}
    h = int(hashlib.sha1(f"{nik}{d}".encode()).hexdigest(), 16)
    end = 840 if d.weekday() == 5 else 960
    late = h % 25 if h % 6 == 0 else 0
    early = (h // 7) % 20 if h % 11 == 0 else 0
    return {**base, "leave_type": "present", "shift_code": "REG", "shift_name": "Reguler",
            "schedule_start": "08:00", "schedule_end": _hhmm(end), "check_in_time": _hhmm(480 + late),
            "check_out_time": _hhmm(end - early), "minutes_late": late, "minutes_early_leave": early,
            "overtime_hours": 2 if h % 9 == 0 and d.weekday() < 5 else 0}


def _mock_rumatku(start: str, end: str, employees: list) -> list:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if start.startswith("2026-03"):
        return [{"nik": "EMP-001", "work_date": f"2026-03-{day:02d}", "leave_type": "present", "shift_code": "REG",
                 "shift_name": "Reguler", "schedule_start": "08:00", "schedule_end": "16:00",
                 "check_in_time": _hhmm(480 + late), "check_out_time": _hhmm(960 - early), "minutes_late": late,
                 "minutes_early_leave": early, "overtime_hours": 0} for day, late, early in BUDI_MARCH]
    out, d = [], s
    while d <= e:
        out += [_mock_day(emp["nik"], d, emp.get("payroll_status")) for emp in employees]
        d += timedelta(days=1)
    return out


def normalize_attendance(r: dict) -> dict:
    lt = r.get("leave_type") or "present"
    if lt not in LEAVE_TYPES:
        raise ValueError(f"leave_type tidak dikenal: {lt}")
    return {
        "work_date": r["work_date"], "leave_type": lt, "check_in_time": r.get("check_in_time"),
        "check_out_time": r.get("check_out_time"), "minutes_late": int(r.get("minutes_late") or 0),
        "minutes_early_leave": int(r.get("minutes_early_leave") or 0),
        "is_missing_check_in": bool(r.get("is_missing_check_in")), "is_missing_check_out": bool(r.get("is_missing_check_out")),
        "overtime_hours": float(r.get("overtime_hours") or 0), "shift_code": r.get("shift_code"),
        "shift_name": r.get("shift_name"), "schedule_start": r.get("schedule_start"), "schedule_end": r.get("schedule_end"),
        "is_off_day": lt == "day_off", "photo_in_url": r.get("photo_in_url"), "photo_out_url": r.get("photo_out_url"),
        "location_in": r.get("location_in"), "location_out": r.get("location_out"), "notes": r.get("notes") or "",
    }


async def fetch_attendance(start: str, end: str, employees: list) -> list:
    if mode("RUMATKU") == "live":
        raw = await _get("RUMATKU", "/attendance", {"start": start, "end": end})
    else:
        raw = _mock_rumatku(start, end, employees)
    return [{"nik": str(r["nik"]).strip(), **normalize_attendance(r)} for r in raw]
