import os
import uuid

from core import db, now_iso, hash_password, verify_password, DEFAULT_CONFIGS
from pipeline import process_period
from schedules import seed_schedules

DEMO_PASSWORD = "Password123!"

EMPLOYEES = [
    {"nik": "EMP-001", "name": "Budi Santoso", "email": "budi@rumatku.id", "department": "Staff Finance",
     "birth_date": "1995-08-15", "gender": "L", "marital_status": "K", "dependents_count": 1,
     "has_husband_certificate": False, "payroll_status": "active", "basic_salary": 6000000,
     "position_allowance": 1200000, "monthly_attendance_allowance": 1000000, "overtime_hourly_rate": 50000,
     "bank_name": "BSI", "bank_account_number": "7123456789"},
    {"nik": "EMP-002", "name": "Siti Aminah", "email": "siti@rumatku.id", "department": "Junior Nurse",
     "birth_date": "1998-04-22", "gender": "P", "marital_status": "K", "dependents_count": 1,
     "has_husband_certificate": False, "payroll_status": "active", "basic_salary": 4500000,
     "position_allowance": 500000, "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0,
     "bank_name": "BSI", "bank_account_number": "7198765432"},
    {"nik": "EMP-003", "name": "Dimas Pratama", "email": "dimas@rumatku.id", "department": "General Affairs",
     "birth_date": "1992-01-10", "gender": "L", "marital_status": "TK", "dependents_count": 0,
     "has_husband_certificate": False, "payroll_status": "unpaid_leave", "basic_salary": 5500000,
     "position_allowance": 800000, "monthly_attendance_allowance": 0, "overtime_hourly_rate": 0,
     "bank_name": "BSI", "bank_account_number": ""},
]

BUDI_MARCH = [(1, 1, 17), (2, 4, 0), (3, 5, 0), (4, 7, 0), (5, 15, 0), (6, 16, 0), (12, 4, 0), (13, 5, 0),
              (16, 6, 0), (17, 2, 0), (18, 4, 20), (20, 18, 0), (22, 6, 0), (23, 3, 0), (25, 0, 15), (27, 3, 0),
              (29, 61, 0), (31, 17, 0)]


def _hhmm(base: int, delta: int) -> str:
    t = base + delta
    return f"{t // 60:02d}:{t % 60:02d}"


async def ensure_user(email, password, name, role, employee_id=None, nik=None):
    email = email.lower()
    u = await db.users.find_one({"email": email})
    if not u:
        await db.users.insert_one({"id": str(uuid.uuid4()), "email": email, "name": name, "role": role, "nik": nik,
                                   "employee_id": employee_id, "password_hash": hash_password(password),
                                   "created_at": now_iso()})
    elif not verify_password(password, u["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})


async def seed():
    await db.users.create_index("email", unique=True)
    await db.employees.create_index("nik", unique=True)
    await db.payslips.create_index([("payroll_period_id", 1), ("employee_id", 1)], unique=True)
    await db.attendance_daily_logs.create_index([("employee_id", 1), ("work_date", 1)], unique=True)
    await db.login_attempts.create_index("identifier")
    for k, (v, desc) in DEFAULT_CONFIGS.items():
        await db.payroll_configs.update_one({"config_key": k}, {"$setOnInsert": {
            "config_key": k, "config_value": v, "description": desc}}, upsert=True)
    await db.payroll_configs.delete_many({"config_key": {"$nin": list(DEFAULT_CONFIGS)}})
    await seed_schedules()
    await db.employees.update_many({"work_schedule_code": {"$exists": False}},
                                   {"$set": {"work_schedule_code": "KANTOR_PUSAT"}})

    await ensure_user("hrd.manager@rumatku.id", DEMO_PASSWORD, "Manager HRD", "manager_hrd")
    await ensure_user(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"], "Admin Payroll", "admin_payroll")

    for e in EMPLOYEES:
        emp = await db.employees.find_one({"nik": e["nik"]})
        if not emp:
            emp = {**e, "id": str(uuid.uuid4()), "prolonged_illness_month_count": 0, "unpaid_leave_start": None,
                   "unpaid_leave_end": None, "has_bpjs_kes": True, "has_bpjs_tk": True, "jkk_rate": 0.0024, "work_schedule_code": "KANTOR_PUSAT",
                   "created_at": now_iso()}
            if e["payroll_status"] == "unpaid_leave":
                emp.update(unpaid_leave_start="2026-03-01", unpaid_leave_end="2026-05-31")
            await db.employees.insert_one({**emp})
        await ensure_user(e["email"], DEMO_PASSWORD, e["name"], "employee", employee_id=emp["id"], nik=e["nik"])

    if await db.payroll_periods.count_documents({}) == 0:
        budi = await db.employees.find_one({"nik": "EMP-001"})
        for day, late, early in BUDI_MARCH:
            await db.attendance_daily_logs.update_one(
                {"employee_id": budi["id"], "work_date": f"2026-03-{day:02d}"},
                {"$setOnInsert": {"id": str(uuid.uuid4()), "check_in_time": _hhmm(480, late),
                                  "check_out_time": _hhmm(960, -early), "minutes_late": late,
                                  "minutes_early_leave": early, "is_missing_check_in": False,
                                  "is_missing_check_out": False, "leave_type": "present", "notes": "",
                                  "source": "seed"}}, upsert=True)
        period = {"id": str(uuid.uuid4()), "period_name": "Maret 2026", "start_date": "2026-03-01",
                  "end_date": "2026-03-31", "payment_date": "2026-03-31", "status": "draft", "approved_by": None,
                  "approved_at": None, "created_at": now_iso()}
        await db.payroll_periods.insert_one({**period})
        await process_period(period)
