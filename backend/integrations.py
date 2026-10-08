"""Adapters for HAM ROSY: employee & salary master, and daily attendance facts (computed by HAM
from RUMATKU check-in data). Live mode when HAM_API_URL is set, otherwise MOCK (simulated JSON).

Live endpoints (HAM, header X-Integrasi-Key, caller RASA, read-only):
  GET {HAM_API_URL}/api/ham/v2/payroll-feed/karyawan?payroll_company_id=&periode=YYYY-MM
  GET {HAM_API_URL}/api/ham/v2/payroll-feed/presensi?payroll_company_id=&start=&end=
Payslip delivery still uses the legacy RUMATKU contract (RUMATKU_API_URL), mock until HAM's slip
endpoint exists."""
import hashlib
import os
from datetime import date, timedelta

import httpx

from engine import resolve_ptkp
from seed import EMPLOYEES, BUDI_MARCH

LEAVE_TYPES = {"present", "sick_with_certificate", "annual_leave", "statutory_leave", "maternity_leave",
               "menstrual_leave", "approved_unpaid_leave", "alpha", "day_off", "permission_leave", "official_duty"}

# status_ham (HAM AbsensiModules::harianBatch) -> leave_type. Initial proposal; must be signed off by HRD
# (Rencana Setting Payroll section B). "ibadah" follows current HAM behaviour (1 point/day, like izin).
LEAVE_MAP = {
    "hadir": "present", "dinas": "official_duty", "izin": "permission_leave", "sakit": "sick_with_certificate",
    "cuti": "annual_leave", "khusus": "statutory_leave", "melahirkan": "maternity_leave",
    "ibadah": "permission_leave", "alfa": "alpha", "dispensasi": "statutory_leave", "libur": "day_off",
}

FEED = "/api/ham/v2/payroll-feed"


def mode(system: str) -> str:
    """ROSY (employees) and RUMATKU (attendance) are both served by HAM's payroll feed."""
    return "live" if os.environ.get("HAM_API_URL") else "mock"


def company_id() -> str:
    return os.environ.get("PAYROLL_COMPANY_ID", "CP-001")


async def _get(path: str, params: dict) -> dict:
    url = os.environ["HAM_API_URL"].rstrip("/") + FEED + path
    headers = {"X-Integrasi-Key": os.environ.get("HAM_INTEGRASI_KEY", ""), "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url, headers=headers, params=params)
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code != 200:
        raise RuntimeError(f"HAM {r.status_code}: {body.get('message') or r.text[:200]}")
    return body


def _mock_rosy() -> list:
    return [{
        "employee_id": f"MOCK-{e['nik']}", "nik": e["nik"], "ktp": None, "name": e["name"], "email": e["email"],
        "gender": e["gender"], "birth_date": e["birth_date"], "ptkp_status": resolve_ptkp(e), "npwp": None,
        "department": e["department"], "position": e["department"], "level": "Staff", "employment_type": "Tetap",
        "is_active": True, "join_date": None, "exit_date": None, "is_paid": e["payroll_status"] != "unpaid_leave",
        "attendance_exempt": False, "user_id_rumatku": None, "payroll_company_id": company_id(),
        "salary": {"basic_salary": e["basic_salary"], "position_allowance": e["position_allowance"],
                   "monthly_attendance_allowance": e["monthly_attendance_allowance"],
                   "overtime_hourly_rate": e["overtime_hourly_rate"]},
        "bpjs": {"kes": True, "jkk": True, "jkm": True, "jht": True, "jp": True, "jkk_rate": 0.0024,
                 "upah_kes": None, "upah_tk": None},
        "bank": {"name": e["bank_name"], "code": None, "account_number": e["bank_account_number"], "account_name": None},
        "data_issues": [],
    } for e in EMPLOYEES]


def normalize_employee(r: dict) -> dict:
    sal, bp, bank = r.get("salary") or {}, r.get("bpjs") or {}, r.get("bank") or {}
    ptkp = r.get("ptkp_status") or "TK/0"
    programs = {p: bool(bp.get(p)) for p in ("kes", "jkk", "jkm", "jht", "jp")}
    nik = str(r.get("nik") or "").strip()
    return {
        "rosy_employee_id": str(r["employee_id"]),
        # HAM's nik is not unique and may be a placeholder; it is only used for display
        "nik": nik if nik not in ("", "-", "0") else str(r["employee_id"]),
        "name": r["name"], "email": (r.get("email") or "").lower(), "department": r.get("department") or "",
        "position": r.get("position") or "", "level": r.get("level") or "",
        "employment_type": r.get("employment_type") or "", "birth_date": r.get("birth_date"),
        "gender": r.get("gender") or "L", "ptkp_status": ptkp,
        "marital_status": "K" if ptkp.startswith("K/") else "TK", "dependents_count": int(ptkp[-1]),
        "has_husband_certificate": False, "npwp": r.get("npwp") or "", "ktp": r.get("ktp") or "",
        "payroll_status": "active" if r.get("is_paid", True) else "unpaid_leave",
        "prolonged_illness_month_count": 0, "attendance_exempt": bool(r.get("attendance_exempt")),
        "join_date": r.get("join_date"), "exit_date": r.get("exit_date"), "is_active": r.get("is_active", True),
        "user_id_rumatku": r.get("user_id_rumatku"), "payroll_company_id": r.get("payroll_company_id"),
        "basic_salary": float(sal.get("basic_salary") or 0), "position_allowance": float(sal.get("position_allowance") or 0),
        "monthly_attendance_allowance": float(sal.get("monthly_attendance_allowance") or 0),
        "overtime_hourly_rate": float(sal.get("overtime_hourly_rate") or 0),
        "has_bpjs_kes": programs["kes"], "has_bpjs_tk": any(programs[p] for p in ("jkk", "jkm", "jht", "jp")),
        "bpjs_programs": programs, "jkk_rate": float(bp.get("jkk_rate") or 0.0024),
        "bank_name": bank.get("name") or "", "bank_code": bank.get("code") or "",
        "bank_account_number": bank.get("account_number") or "", "bank_account_name": bank.get("account_name") or "",
        "overtime_access": bool(r.get("lembur_akses")), "data_issues": list(r.get("data_issues") or []),
    }


async def fetch_employees(periode: str) -> tuple:
    """Returns (employees, meta). periode = 'YYYY-MM'."""
    if mode("ROSY") == "live":
        body = await _get("/karyawan", {"payroll_company_id": company_id(), "periode": periode})
        raw, meta = body.get("data") or [], body.get("meta") or {}
    else:
        raw, meta = _mock_rosy(), {"dilewati": [], "company": None}
    return [normalize_employee(r) for r in raw], meta


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
    status = r.get("status_ham")
    if status is not None:
        if status not in LEAVE_MAP:
            raise ValueError(f"status_ham tidak dikenal: {status}")
        lt = LEAVE_MAP[status]
    else:
        lt = r.get("leave_type") or "present"
    if lt not in LEAVE_TYPES:
        raise ValueError(f"leave_type tidak dikenal: {lt}")
    notes = r.get("notes") or ""
    if status == "sakit" and r.get("has_document") is False:
        notes = (notes + " " if notes else "") + "Sakit tanpa lampiran surat"
    return {
        "work_date": r["work_date"], "leave_type": lt, "check_in_time": r.get("check_in_time"),
        "check_out_time": r.get("check_out_time"), "minutes_late": int(r.get("minutes_late") or 0),
        "minutes_early_leave": int(r.get("minutes_early_leave") or 0),
        "is_missing_check_in": bool(r.get("is_missing_check_in")), "is_missing_check_out": bool(r.get("is_missing_check_out")),
        "overtime_hours": float(r.get("overtime_hours") or 0), "shift_code": r.get("shift_code"),
        "shift_name": r.get("shift_name"), "schedule_start": r.get("schedule_start"), "schedule_end": r.get("schedule_end"),
        "is_off_day": lt == "day_off", "photo_in_url": r.get("photo_in_url"), "photo_out_url": r.get("photo_out_url"),
        "location_in": r.get("location_in"), "location_out": r.get("location_out"), "notes": notes,
        "status_ham": status, "ham_points": r.get("ham_points"), "excused": bool(r.get("excused")),
        "leave_category_id": r.get("leave_category_id"), "has_document": r.get("has_document"),
    }


async def push_payslip(slip: dict, period: dict, pdf_path: str) -> dict:
    nik = slip["employee"]["nik"]
    if not os.environ.get("RUMATKU_API_URL"):
        if nik in os.environ.get("RUMATKU_MOCK_FAIL_NIKS", "").split(","):
            raise RuntimeError("Simulasi: RUMATKU tidak merespons")
        return {"ref": f"MOCK-{slip['id'][:8]}"}
    url = os.environ["RUMATKU_API_URL"].rstrip("/") + "/payslips"
    headers = {"Authorization": f"Bearer {os.environ.get('RUMATKU_API_KEY', '')}", "Accept": "application/json"}
    meta = {"nik": nik, "period_name": period["period_name"], "start_date": period["start_date"],
            "end_date": period["end_date"], "take_home_pay": str(slip["take_home_pay"])}
    async with httpx.AsyncClient(timeout=60) as c:
        with open(pdf_path, "rb") as f:
            r = await c.post(url, headers=headers, data=meta, files={"file": (f"Slip-{nik}.pdf", f, "application/pdf")})
        r.raise_for_status()
        body = r.json() if r.content else {}
    return {"ref": (body.get("data") or body).get("id") if isinstance(body, dict) else None}


async def fetch_overtime(periode_bayar: str):
    """Approved overtime claims paid in this payslip month (HAM lembur, rumatku.mt_lembur).

    Returns (claims, meta) in live mode, or None in mock mode — the simulation keeps overtime in the
    daily logs. Pay month is periode_bayar, not the claim date: a late-approved claim moves to the next slip."""
    if mode("RUMATKU") != "live":
        return None
    body = await _get("/lembur", {"payroll_company_id": company_id(), "periode_bayar": periode_bayar})
    claims = [{"claim_id": int(r["claim_id"]), "rosy_employee_id": str(r["employee_id"]), "tanggal": r["tanggal"],
               "jam_mulai": r.get("jam_mulai"), "jam_selesai": r.get("jam_selesai"),
               "menit_diklaim": int(r.get("menit_diklaim") or 0), "menit_disetujui": int(r["menit_disetujui"]),
               "periode_bayar": r["periode_bayar"], "approved_at": r.get("approved_at")}
              for r in body.get("data") or []]
    return claims, body.get("meta") or {}


async def fetch_attendance(start: str, end: str, employees: list) -> tuple:
    """Returns (rows, meta). Live rows are keyed by rosy_employee_id; mock rows by nik."""
    if mode("RUMATKU") == "live":
        body = await _get("/presensi", {"payroll_company_id": company_id(), "start": start, "end": end})
        raw, meta = body.get("data") or [], body.get("meta") or {}
        return [{"rosy_employee_id": str(r["employee_id"]), **normalize_attendance(r)} for r in raw], meta
    raw = _mock_rumatku(start, end, employees)
    return [{"nik": str(r["nik"]).strip(), **normalize_attendance(r)} for r in raw], {"unlinked": []}
