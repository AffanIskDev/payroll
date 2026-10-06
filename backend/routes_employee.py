import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core import db, now_iso, require_employee, get_configs
from pipeline import get_period
from pdf_service import save_encrypted

router = APIRouter(prefix="/api/v1/employee")
WIB = timezone(timedelta(hours=7))
SUMMARY_FIELDS = {"_id": 0, "discipline": 0, "bpjs": 0, "pdf_path": 0, "pdf_password_hash": 0}


async def _with_period(slip: dict) -> dict:
    p = await db.payroll_periods.find_one({"id": slip["payroll_period_id"]}, {"_id": 0})
    slip["period"] = p
    return slip


@router.get("/payslips")
async def my_payslips(user: dict = Depends(require_employee)):
    slips = await db.payslips.find({"employee_id": user["employee_id"], "status": "approved"}, SUMMARY_FIELDS) \
        .to_list(200)
    slips = [await _with_period(s) for s in slips]
    return sorted(slips, key=lambda s: s["period"]["start_date"], reverse=True)


async def _own_slip(sid: str, user: dict, projection=None) -> dict:
    slip = await db.payslips.find_one({"id": sid, "employee_id": user["employee_id"], "status": "approved"},
                                      projection or {"_id": 0})
    if not slip:
        raise HTTPException(404, "Slip tidak ditemukan")
    return slip


@router.get("/payslips/{sid}")
async def my_payslip(sid: str, user: dict = Depends(require_employee)):
    slip = await _own_slip(sid, user, {"_id": 0, "pdf_path": 0, "pdf_password_hash": 0})
    return await _with_period(slip)


@router.get("/payslips/{sid}/download")
async def download(sid: str, user: dict = Depends(require_employee)):
    slip = await _own_slip(sid, user)
    path = slip.get("pdf_path")
    if not path or not Path(path).exists():
        path = save_encrypted(slip, await get_period(slip["payroll_period_id"]))
        await db.payslips.update_one({"id": sid}, {"$set": {"pdf_path": path}})
    p = slip.get("payroll_period_id")
    period = await get_period(p)
    name = f"Slip-Gaji-{slip['employee']['nik']}-{period['period_name'].replace(' ', '-')}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get("/profile")
async def profile(user: dict = Depends(require_employee)):
    emp = await db.employees.find_one({"id": user["employee_id"]}, {"_id": 0})
    return {k: emp.get(k) for k in ("nik", "name", "email", "department", "bank_name", "bank_account_number",
                                    "payroll_status")}


def _today():
    n = datetime.now(WIB)
    return n.strftime("%Y-%m-%d"), n.strftime("%H:%M"), n.hour * 60 + n.minute


def _mins(t: str) -> int:
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


@router.get("/attendance/today")
async def today(user: dict = Depends(require_employee)):
    d, _, _ = _today()
    log = await db.attendance_daily_logs.find_one({"employee_id": user["employee_id"], "work_date": d}, {"_id": 0})
    return {"date": d, "log": log}


@router.post("/attendance/clock-in")
async def clock_in(user: dict = Depends(require_employee)):
    d, hhmm, mins = _today()
    cfg = await get_configs()
    eid = user["employee_id"]
    if await db.attendance_daily_logs.find_one({"employee_id": eid, "work_date": d, "check_in_time": {"$ne": None}}):
        raise HTTPException(400, "Anda sudah absen masuk hari ini")
    late = max(0, mins - _mins(cfg["WORK_START_TIME"]))
    data = {"check_in_time": hhmm, "minutes_late": late, "is_missing_check_in": False, "leave_type": "present",
            "source": "rumatku", "updated_at": now_iso()}
    res = await db.attendance_daily_logs.update_one(
        {"employee_id": eid, "work_date": d}, {"$set": data,
                                               "$setOnInsert": {"id": str(uuid.uuid4()), "check_out_time": None,
                                                                "minutes_early_leave": 0, "is_missing_check_out": False,
                                                                "notes": ""}}, upsert=True)
    return {"date": d, **data, "upserted": bool(res.upserted_id)}


@router.post("/attendance/clock-out")
async def clock_out(user: dict = Depends(require_employee)):
    d, hhmm, mins = _today()
    cfg = await get_configs()
    eid = user["employee_id"]
    log = await db.attendance_daily_logs.find_one({"employee_id": eid, "work_date": d})
    if log and log.get("check_out_time"):
        raise HTTPException(400, "Anda sudah absen pulang hari ini")
    early = max(0, _mins(cfg["WORK_END_TIME"]) - mins)
    data = {"check_out_time": hhmm, "minutes_early_leave": early, "is_missing_check_out": False,
            "source": "rumatku", "updated_at": now_iso()}
    await db.attendance_daily_logs.update_one(
        {"employee_id": eid, "work_date": d},
        {"$set": data, "$setOnInsert": {"id": str(uuid.uuid4()), "check_in_time": None, "minutes_late": 0,
                                        "is_missing_check_in": True, "leave_type": "present", "notes": ""}},
        upsert=True)
    return {"date": d, **data}
