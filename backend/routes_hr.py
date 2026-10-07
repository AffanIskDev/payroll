import uuid
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core import db, now_iso, require_hr, require_manager, hash_password, get_configs, DEFAULT_CONFIGS
from schedules import detect_shift, minutes_for, shift_fields
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
                     total_bpjs_kes=sum(s["iuran_bpjs_kes_total"] for s in slips),
                     total_bpjs_tk=sum(s["iuran_bpjs_tk_total"] for s in slips),
                     pending=sum(1 for s in slips if s["status"] != "approved"),
                     approved=sum(1 for s in slips if s["status"] == "approved"))
    return stats


@router.get("/notifications")
async def notifications(user: dict = Depends(require_hr)):
    if user["role"] == "manager_hrd":
        q, kind = {"status": "pending_approval"}, "submitted"
    else:
        q, kind = {"status": "revision"}, "rejected"
    periods = await db.payroll_periods.find(q, {"_id": 0}).sort("start_date", -1).to_list(100)
    return [{"kind": kind, "period_id": p["id"], "period_name": p["period_name"],
             "by": p.get("submitted_by") if kind == "submitted" else p.get("rejected_by"),
             "at": p.get("submitted_at") if kind == "submitted" else p.get("rejected_at"),
             "reason": p.get("rejection_reason") if kind == "rejected" else None} for p in periods]


@router.get("/configs")
async def list_configs():
    return await db.payroll_configs.find({}, {"_id": 0}).sort("config_key", 1).to_list(100)


@router.put("/configs")
async def update_configs(body: dict):
    for k, v in body.items():
        if k not in DEFAULT_CONFIGS:
            raise HTTPException(400, f"Config tidak dikenal: {k}")
        if k == "CSV_DELIMITER" and str(v) not in (",", ";", "|", "tab"):
            raise HTTPException(400, "Pemisah CSV harus , ; | atau tab")
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
    shift, src = None, "auto"
    if data["leave_type"] == "present":
        shift, src = await detect_shift(emp, data["work_date"], data["check_in_time"], data["check_out_time"],
                                        data["shift_code"])
    late, early = minutes_for(shift, data["check_in_time"], data["check_out_time"])
    if data["minutes_late"] is None:
        data["minutes_late"] = late
    if data["minutes_early_leave"] is None:
        data["minutes_early_leave"] = early
    data.update(shift_fields(shift, src), is_off_day=data["leave_type"] == "present" and shift is None)
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
    if period["status"] not in EDITABLE_STATUSES + ("pending_approval",) or \
            await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Hanya periode yang belum memiliki slip approved yang dapat dihapus")
    res = await db.payslips.delete_many({"payroll_period_id": pid})
    await db.payroll_periods.delete_one({"id": pid})
    return {"ok": True, "deleted_payslips": res.deleted_count}


EDITABLE_STATUSES = ("draft", "revision")


async def _log(pid: str, action: str, user: dict, reason: str = "", extra: Optional[dict] = None):
    entry = {"action": action, "by": user["email"], "by_name": user.get("name"), "at": now_iso(), "reason": reason}
    await db.payroll_periods.update_one({"id": pid}, {"$set": extra or {}, "$push": {"review_history": entry}})


class RejectIn(BaseModel):
    reason: str


@router.post("/periods/{pid}/process")
async def run_process(pid: str):
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci")
    count = await process_period(period)
    return {"processed": count}


@router.post("/periods/{pid}/submit")
async def submit_period(pid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Hanya periode draft / revisi yang dapat diajukan")
    if not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    await _log(pid, "submitted", user, extra={"status": "pending_approval", "submitted_by": user["email"],
                                              "submitted_at": now_iso()})
    return await get_period(pid)


@router.post("/periods/{pid}/reject")
async def reject_period(pid: str, body: RejectIn, user: dict = Depends(require_manager)):
    period = await get_period(pid)
    reason = body.reason.strip()
    if len(reason) < 5:
        raise HTTPException(400, "Alasan penolakan wajib diisi (min. 5 karakter)")
    if period["status"] != "pending_approval":
        raise HTTPException(400, "Hanya periode yang menunggu approval yang dapat ditolak")
    if await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Sebagian slip sudah di-approve; tidak dapat ditolak")
    await _log(pid, "rejected", user, reason, {"status": "revision", "rejection_reason": reason,
                                               "rejected_by": user["email"], "rejected_at": now_iso()})
    return await get_period(pid)


@router.post("/periods/{pid}/approve-all")
async def approve_all(pid: str, user: dict = Depends(require_manager)):
    period = await get_period(pid)
    if period["status"] != "pending_approval":
        raise HTTPException(400, "Periode harus diajukan ke Manager terlebih dahulu")
    slips = await db.payslips.find({"payroll_period_id": pid, "status": {"$ne": "approved"}}, {"_id": 0}).to_list(2000)
    if not slips and not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    for s in slips:
        await approve_slip(s, period, user)
    await _log(pid, "approved", user)
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
async def save_draft(pid: str, eid: str, body: AdjustIn, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    emp = await get_employee(eid)
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve & dikunci")
    if period["status"] not in EDITABLE_STATUSES and user["role"] != "manager_hrd":
        raise HTTPException(400, "Periode sedang direview Manager; tidak dapat diubah")
    adj = {k: getattr(body, k) for k in ADJ_KEYS}
    return await recalc_and_save(period, emp, adj, notes=body.adjustment_notes, manual=True)


@router.post("/periods/{pid}/employees/{eid}/approve")
async def approve_one(pid: str, eid: str, user: dict = Depends(require_manager)):
    period = await get_period(pid)
    if period["status"] != "pending_approval":
        raise HTTPException(400, "Periode harus diajukan ke Manager terlebih dahulu")
    slip = await _slip(pid, eid)
    if slip["status"] == "approved":
        raise HTTPException(400, "Slip sudah di-approve")
    return await approve_slip(slip, period, user)


@router.get("/periods/{pid}/employees/{eid}/pdf")
async def preview_pdf(pid: str, eid: str):
    period = await get_period(pid)
    slip = await _slip(pid, eid)
    return Response(render_payslip(slip, period, await get_configs()), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="preview-{slip["employee"]["nik"]}.pdf"'})
