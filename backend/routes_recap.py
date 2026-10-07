from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core import db, require_hr

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])


def _month(month: str) -> tuple:
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(400, "Format bulan harus YYYY-MM")
    return first, (first.replace(day=28) + timedelta(days=4)).replace(day=1)


@router.get("/shift-recap")
async def shift_recap(month: str):
    first, nxt = _month(month)
    days = (nxt - first).days
    emps = await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(5000)
    logs = await db.attendance_daily_logs.find(
        {"work_date": {"$gte": first.isoformat(), "$lt": nxt.isoformat()}}, {"_id": 0}).to_list(100000)
    by_emp, names = {}, {}
    for lg in logs:
        by_emp.setdefault(lg["employee_id"], []).append(lg)
        if lg.get("shift_code"):
            names.setdefault(lg["shift_code"], lg.get("shift_name") or lg["shift_code"])
    rows = []
    for e in emps:
        mine = by_emp.get(e["id"], [])
        r = {"employee_id": e["id"], "nik": e["nik"], "name": e["name"], "department": e.get("department"),
             "shifts": {}, "off_days": 0, "leave": 0, "present_no_shift": 0}
        for lg in mine:
            lt = lg.get("leave_type", "present")
            if lt == "day_off" or lg.get("is_off_day"):
                r["off_days"] += 1
            elif lt != "present":
                r["leave"] += 1
            elif lg.get("shift_code"):
                r["shifts"][lg["shift_code"]] = r["shifts"].get(lg["shift_code"], 0) + 1
            else:
                r["present_no_shift"] += 1
        r["total_worked"] = sum(r["shifts"].values()) + r["present_no_shift"]
        r["no_log"] = days - len(mine)
        rows.append(r)
    codes = sorted(names)
    return {"month": month, "days_in_month": days, "shift_codes": codes, "shift_names": names, "rows": rows}


@router.get("/overtime-recap")
async def overtime_recap(month: str):
    first, nxt = _month(month)
    periods = {p["id"]: p async for p in db.payroll_periods.find(
        {"end_date": {"$gte": first.isoformat(), "$lt": nxt.isoformat()}}, {"_id": 0})}
    slips = await db.payslips.find({"payroll_period_id": {"$in": list(periods)}}, {"_id": 0}) \
        .sort("employee.nik", 1).to_list(5000)
    emps = {e["id"]: e async for e in db.employees.find({}, {"_id": 0, "id": 1, "overtime_hourly_rate": 1})}
    rows = [{"employee_id": s["employee_id"], "nik": s["employee"]["nik"], "name": s["employee"]["name"],
             "department": s["employee"].get("department"), "period_name": periods[s["payroll_period_id"]]["period_name"],
             "overtime_hours": s.get("overtime_hours", 0),
             "overtime_rate": emps.get(s["employee_id"], {}).get("overtime_hourly_rate", 0),
             "overtime_pay": s.get("overtime_pay", 0), "slip_status": s["status"]} for s in slips]
    return {"month": month, "rows": rows, "total_hours": sum(r["overtime_hours"] for r in rows),
            "total_pay": sum(r["overtime_pay"] for r in rows)}
