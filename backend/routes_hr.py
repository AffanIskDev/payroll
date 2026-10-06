import uuid
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core import db, now_iso, require_hr, hash_password, DEFAULT_CONFIGS
from schedules import employee_schedule, resolve_shift, minutes_for
from pipeline import (get_period, get_employee, period_logs, build_slip, recalc_and_save, process_period,
                      approve_slip, ADJ_KEYS)
from pdf_service import render_payslip

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])

LeaveType = Literal["present", "sick_with_certificate", "annual_leave", "statutory_leave", "maternity_leave",
                    "menstrual_leave", "approved_unpaid_leave", "alpha"]
PayrollStatus = Literal["active", "unpaid_leave", "prolonged_illness", "work_accident_stmb"]


class EmployeeIn(BaseModel):
    nik: str
    name: str
    email: str
    department: str = ""
    birth_date: str
    gender: Literal["L", "P"]
    marital_status: Literal["TK", "K"]
    dependents_count: int = 0
    has_husband_certificate: bool = False
    payroll_status: PayrollStatus = "active"
    prolonged_illness_month_count: int = 0
    unpaid_leave_start: Optional[str] = None
    unpaid_leave_end: Optional[str] = None
    basic_salary: float
    position_allowance: float = 0
    monthly_attendance_allowance: float = 0
    overtime_hourly_rate: float = 0
    has_bpjs_kes: bool = True
    has_bpjs_tk: bool = True
    jkk_rate: float = 0.0024
    bank_name: str = "BSI"
    bank_account_number: str = ""
    npwp: str = ""
    work_schedule_code: str = "KANTOR_PUSAT"
    password: Optional[str] = None


class AttendanceIn(BaseModel):
    employee_id: str
    work_date: str
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    minutes_late: Optional[int] = None
    minutes_early_leave: Optional[int] = None
    is_missing_check_in: bool = False
    is_missing_check_out: bool = False
    leave_type: LeaveType = "present"
    shift_code: Optional[str] = None
    notes: str = ""


class PeriodIn(BaseModel):
    period_name: str
    start_date: str
    end_date: str
    payment_date: Optional[str] = None


class AdjustIn(BaseModel):
    overtime_hours: float = 0
    kpi_incentive: float = 0
    additional_bonus: float = 0
    late_penalty_compensation: float = 0
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
                     pending=sum(1 for s in slips if s["status"] != "approved"),
                     approved=sum(1 for s in slips if s["status"] == "approved"))
    return stats


@router.get("/configs")
async def list_configs():
    return await db.payroll_configs.find({}, {"_id": 0}).sort("config_key", 1).to_list(100)


@router.put("/configs")
async def update_configs(body: dict):
    for k, v in body.items():
        if k not in DEFAULT_CONFIGS:
            raise HTTPException(400, f"Config tidak dikenal: {k}")
        await db.payroll_configs.update_one({"config_key": k}, {"$set": {"config_value": str(v)}})
    return await list_configs()


class ShiftIn(BaseModel):
    code: str
    name: str
    days: dict


class ScheduleIn(BaseModel):
    name: str
    shifts: list[ShiftIn]


@router.get("/schedules")
async def list_schedules():
    return await db.work_schedules.find({}, {"_id": 0}).sort("code", 1).to_list(100)


@router.put("/schedules/{code}")
async def update_schedule(code: str, body: ScheduleIn):
    if not await db.work_schedules.find_one({"code": code}):
        raise HTTPException(404, "Jadwal tidak ditemukan")
    shifts = []
    for s in body.shifts:
        days = {}
        for k, v in s.days.items():
            if k not in [str(i) for i in range(7)]:
                raise HTTPException(400, f"Hari tidak valid: {k}")
            if v and v.get("start") and v.get("end"):
                if v["start"] >= v["end"]:
                    raise HTTPException(400, f"{s.name}: jam masuk harus sebelum jam pulang")
                days[k] = {"start": v["start"][:5], "end": v["end"][:5]}
        shifts.append({"code": s.code, "name": s.name, "days": days})
    await db.work_schedules.update_one({"code": code}, {"$set": {"name": body.name, "shifts": shifts}})
    return await db.work_schedules.find_one({"code": code}, {"_id": 0})


@router.get("/employees")
async def list_employees():
    return await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(2000)


async def _sync_user(emp: dict, password: Optional[str]):
    user = await db.users.find_one({"employee_id": emp["id"]})
    fields = {"email": emp["email"].lower(), "nik": emp["nik"], "name": emp["name"]}
    if user:
        if password:
            fields["password_hash"] = hash_password(password)
        await db.users.update_one({"employee_id": emp["id"]}, {"$set": fields})
    else:
        await db.users.insert_one({"id": str(uuid.uuid4()), "role": "employee", "employee_id": emp["id"],
                                   "password_hash": hash_password(password or "Password123!"),
                                   "created_at": now_iso(), **fields})


@router.post("/employees")
async def create_employee(body: EmployeeIn):
    data = body.model_dump(exclude={"password"})
    if await db.employees.find_one({"nik": data["nik"]}):
        raise HTTPException(400, "NIK sudah terdaftar")
    if await db.users.find_one({"email": data["email"].lower()}):
        raise HTTPException(400, "Email sudah terdaftar")
    data.update(id=str(uuid.uuid4()), created_at=now_iso())
    await db.employees.insert_one({**data})
    await _sync_user(data, body.password)
    data.pop("_id", None)
    return data


@router.put("/employees/{eid}")
async def update_employee(eid: str, body: EmployeeIn):
    await get_employee(eid)
    data = body.model_dump(exclude={"password"})
    await db.employees.update_one({"id": eid}, {"$set": data})
    emp = await get_employee(eid)
    await _sync_user(emp, body.password)
    return emp


@router.get("/attendance")
async def list_attendance(employee_id: str, start: str, end: str):
    return await db.attendance_daily_logs.find(
        {"employee_id": employee_id, "work_date": {"$gte": start, "$lte": end}}, {"_id": 0}
    ).sort("work_date", 1).to_list(400)


@router.post("/attendance")
async def upsert_attendance(body: AttendanceIn):
    emp = await get_employee(body.employee_id)
    data = body.model_dump()
    shift = None
    if data["leave_type"] == "present":
        shift = resolve_shift(await employee_schedule(emp), data["work_date"], data["check_in_time"],
                              data["check_out_time"], data["shift_code"])
    late, early = minutes_for(shift, data["check_in_time"], data["check_out_time"])
    if data["minutes_late"] is None:
        data["minutes_late"] = late
    if data["minutes_early_leave"] is None:
        data["minutes_early_leave"] = early
    data.update(shift_code=shift and shift["code"], shift_name=shift and shift["name"],
                schedule_start=shift and shift["start"], schedule_end=shift and shift["end"],
                is_off_day=data["leave_type"] == "present" and shift is None)
    data.update(source="hrd_manual", updated_at=now_iso())
    existing = await db.attendance_daily_logs.find_one({"employee_id": body.employee_id, "work_date": body.work_date})
    if existing:
        await db.attendance_daily_logs.update_one({"_id": existing["_id"]}, {"$set": data})
        data["id"] = existing["id"]
    else:
        data["id"] = str(uuid.uuid4())
        await db.attendance_daily_logs.insert_one({**data})
    return data


@router.delete("/attendance/{log_id}")
async def delete_attendance(log_id: str):
    res = await db.attendance_daily_logs.delete_one({"id": log_id})
    if not res.deleted_count:
        raise HTTPException(404, "Log tidak ditemukan")
    return {"ok": True}


@router.get("/periods")
async def list_periods():
    return await db.payroll_periods.find({}, {"_id": 0}).sort("start_date", -1).to_list(100)


@router.post("/periods")
async def create_period(body: PeriodIn):
    data = body.model_dump()
    data.update(id=str(uuid.uuid4()), status="draft", approved_by=None, approved_at=None, created_at=now_iso())
    await db.payroll_periods.insert_one({**data})
    data.pop("_id", None)
    return data


@router.get("/periods/{pid}")
async def period_detail(pid: str):
    period = await get_period(pid)
    slips = await db.payslips.find({"payroll_period_id": pid}, {"_id": 0, "discipline": 0, "bpjs": 0}) \
        .sort("employee.nik", 1).to_list(2000)
    return {"period": period, "payslips": slips}


@router.delete("/periods/{pid}")
async def delete_period(pid: str):
    period = await get_period(pid)
    if period["status"] not in ("draft", "pending_approval") or \
            await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Hanya periode yang belum memiliki slip approved yang dapat dihapus")
    res = await db.payslips.delete_many({"payroll_period_id": pid})
    await db.payroll_periods.delete_one({"id": pid})
    return {"ok": True, "deleted_payslips": res.deleted_count}


@router.post("/periods/{pid}/process")
async def run_process(pid: str):
    period = await get_period(pid)
    if period["status"] in ("approved", "closed"):
        raise HTTPException(400, "Periode sudah dikunci")
    count = await process_period(period)
    return {"processed": count}


@router.post("/periods/{pid}/approve-all")
async def approve_all(pid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    slips = await db.payslips.find({"payroll_period_id": pid, "status": {"$ne": "approved"}}, {"_id": 0}).to_list(2000)
    if not slips and not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    for s in slips:
        await approve_slip(s, period, user)
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
    return {"period": period, "employee": emp, "payslip": slip, "attendance": await period_logs(eid, period)}


@router.post("/periods/{pid}/employees/{eid}/preview")
async def preview(pid: str, eid: str, body: AdjustIn):
    period = await get_period(pid)
    emp = await get_employee(eid)
    return await build_slip(period, emp, body.model_dump())


@router.put("/periods/{pid}/employees/{eid}")
async def save_draft(pid: str, eid: str, body: AdjustIn):
    period = await get_period(pid)
    emp = await get_employee(eid)
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve & dikunci")
    adj = {k: getattr(body, k) for k in ADJ_KEYS}
    return await recalc_and_save(period, emp, adj, notes=body.adjustment_notes, manual=True)


@router.post("/periods/{pid}/employees/{eid}/approve")
async def approve_one(pid: str, eid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve")
    return await approve_slip(slip, period, user)


@router.get("/periods/{pid}/employees/{eid}/pdf")
async def preview_pdf(pid: str, eid: str):
    period = await get_period(pid)
    slip = await _slip(pid, eid)
    return Response(render_payslip(slip, period), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="preview-{slip["employee"]["nik"]}.pdf"'})
