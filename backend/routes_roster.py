import csv
import io
import uuid
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from core import db, now_iso, require_hr, get_configs, csv_delimiter
from routes_tax import _rows_from_upload
from schedules import detect_shift, minutes_for, shift_fields, week_start

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])

ALIASES = {
    "nik": ("nik", "nik_karyawan", "employee_nik"),
    "tanggal": ("tanggal", "date", "work_date"),
    "jam_masuk": ("jam_masuk", "check_in", "check_in_time", "clock_in"),
    "jam_pulang": ("jam_pulang", "check_out", "check_out_time", "clock_out"),
    "foto_masuk": ("foto_masuk", "photo_in", "foto_wajah_masuk"),
    "foto_pulang": ("foto_pulang", "photo_out", "foto_wajah_pulang"),
    "lokasi_masuk": ("lokasi_masuk", "location_in", "gps_masuk"),
    "lokasi_pulang": ("lokasi_pulang", "location_out", "gps_pulang"),
    "keterangan": ("keterangan", "notes", "catatan"),
}
TEMPLATE_COLUMNS = list(ALIASES)


class Assignment(BaseModel):
    employee_id: str
    week_start: str
    shift_code: Optional[str] = None


class RotationIn(BaseModel):
    assignments: list[Assignment]


@router.get("/shift-rotations")
async def list_rotations(start: str, weeks: int = 4):
    ws = week_start(start)
    end = (date.fromisoformat(ws) + timedelta(weeks=weeks)).isoformat()
    scheds = {s["code"]: s async for s in db.work_schedules.find({}, {"_id": 0})}
    multi = [c for c, s in scheds.items() if len(s["shifts"]) > 1]
    emps = await db.employees.find({"work_schedule_code": {"$in": multi}}, {"_id": 0}).sort("nik", 1).to_list(2000)
    rots = await db.shift_rotations.find({"week_start": {"$gte": ws, "$lt": end}}, {"_id": 0}).to_list(10000)
    return {
        "weeks": [(date.fromisoformat(ws) + timedelta(weeks=i)).isoformat() for i in range(weeks)],
        "employees": [{"id": e["id"], "nik": e["nik"], "name": e["name"], "department": e.get("department"),
                       "schedule_code": e["work_schedule_code"],
                       "shifts": [{"code": s["code"], "name": s["name"]} for s in scheds[e["work_schedule_code"]]["shifts"]]}
                      for e in emps],
        "assignments": rots,
    }


@router.put("/shift-rotations")
async def save_rotations(body: RotationIn):
    saved = 0
    for a in body.assignments:
        ws = week_start(a.week_start)
        if not a.shift_code:
            await db.shift_rotations.delete_one({"employee_id": a.employee_id, "week_start": ws})
            continue
        emp = await db.employees.find_one({"id": a.employee_id}, {"_id": 0})
        if not emp:
            raise HTTPException(404, "Karyawan tidak ditemukan")
        sched = await db.work_schedules.find_one({"code": emp.get("work_schedule_code") or "KANTOR_PUSAT"}, {"_id": 0})
        if a.shift_code not in [s["code"] for s in sched["shifts"]]:
            raise HTTPException(400, f"Shift {a.shift_code} tidak ada di jadwal {sched['code']} ({emp['nik']})")
        await db.shift_rotations.update_one(
            {"employee_id": a.employee_id, "week_start": ws},
            {"$set": {"shift_code": a.shift_code, "updated_at": now_iso()}, "$setOnInsert": {"id": str(uuid.uuid4())}},
            upsert=True)
        saved += 1
    return {"saved": saved}


@router.get("/shift-recap")
async def shift_recap(month: str):
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(400, "Format bulan harus YYYY-MM")
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    days = [(first + timedelta(days=i)) for i in range((nxt - first).days)]
    scheds = {s["code"]: s async for s in db.work_schedules.find({}, {"_id": 0})}
    emps = await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(5000)
    logs = await db.attendance_daily_logs.find(
        {"work_date": {"$gte": first.isoformat(), "$lt": nxt.isoformat()}}, {"_id": 0}).to_list(100000)
    by_emp = {}
    for lg in logs:
        by_emp.setdefault(lg["employee_id"], {})[lg["work_date"]] = lg
    codes, rows = [], []
    for e in emps:
        sched = scheds[e.get("work_schedule_code") or "KANTOR_PUSAT"]
        for s in sched["shifts"]:
            if s["code"] not in codes:
                codes.append(s["code"])
        r = {"employee_id": e["id"], "nik": e["nik"], "name": e["name"], "department": e.get("department"),
             "schedule_code": sched["code"], "shifts": {}, "scheduled_off": 0, "worked_on_off_day": 0,
             "leave": 0, "no_log": 0}
        mine = by_emp.get(e["id"], {})
        for d in days:
            wd = str(d.weekday())
            is_off = not any(s["days"].get(wd, {}).get("start") for s in sched["shifts"])
            lg = mine.get(d.isoformat())
            if lg and lg.get("leave_type", "present") != "present":
                r["leave"] += 1
            elif lg and lg.get("shift_code") and not lg.get("is_off_day"):
                r["shifts"][lg["shift_code"]] = r["shifts"].get(lg["shift_code"], 0) + 1
            elif lg and is_off:
                r["worked_on_off_day"] += 1
            elif is_off:
                r["scheduled_off"] += 1
            else:
                r["no_log"] += 1
        r["total_worked"] = sum(r["shifts"].values()) + r["worked_on_off_day"]
        rows.append(r)
    names = {}
    for s in scheds.values():
        for sh in s["shifts"]:
            names.setdefault(sh["code"], sh["name"])
    return {"month": month, "days_in_month": len(days), "shift_codes": codes,
            "shift_names": {c: names[c] for c in codes}, "rows": rows}


@router.get("/overtime-recap")
async def overtime_recap(month: str):
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(400, "Format bulan harus YYYY-MM")
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
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


def _pick(row: dict, key: str):
    for a in ALIASES[key]:
        v = row.get(a)
        if v not in (None, ""):
            return v
    return None


def _date(v) -> str:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"format tanggal tidak dikenal '{s}'")


def _time(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (datetime, time)):
        return f"{v.hour:02d}:{v.minute:02d}"
    s = str(v).strip().replace(".", ":")
    if " " in s:
        s = s.split(" ")[-1]
    h, m = s.split(":")[:2]
    if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
        raise ValueError(f"jam tidak valid '{v}'")
    return f"{int(h):02d}:{int(m):02d}"


@router.get("/attendance/import-template")
async def import_template():
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=csv_delimiter(await get_configs()))
    w.writerow(TEMPLATE_COLUMNS)
    w.writerow(["EMP-001", "2026-04-06", "08:05", "16:00", "https://contoh.rumatku.id/foto/in.jpg",
                "https://contoh.rumatku.id/foto/out.jpg", "-6.2615,107.1520", "-6.2615,107.1521", ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="template_absensi_rumatku.csv"'})


@router.post("/attendance/import")
async def import_attendance(file: UploadFile = File(...)):
    try:
        rows = _rows_from_upload(file.filename or "", await file.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"File tidak dapat dibaca: {e}")
    emps = {e["nik"]: e async for e in db.employees.find({}, {"_id": 0})}
    created = updated = 0
    errors, skipped, shifts = [], [], {}
    for i, r in enumerate(rows, start=2):
        nik = str(_pick(r, "nik") or "").strip()
        emp = emps.get(nik)
        if not emp:
            errors.append(f"Baris {i}: NIK '{nik}' tidak ditemukan")
            continue
        try:
            wd = _date(_pick(r, "tanggal"))
            cin, cout = _time(_pick(r, "jam_masuk")), _time(_pick(r, "jam_pulang"))
        except (ValueError, TypeError) as e:
            errors.append(f"Baris {i}: {e}")
            continue
        if not cin and not cout:
            errors.append(f"Baris {i}: jam masuk & jam pulang kosong")
            continue
        existing = await db.attendance_daily_logs.find_one({"employee_id": emp["id"], "work_date": wd})
        if existing and existing.get("leave_type", "present") != "present":
            skipped.append(f"Baris {i}: {nik} {wd} sudah tercatat {existing['leave_type']} oleh HRD")
            continue
        manual = existing.get("shift_code") if existing and existing.get("shift_source") == "manual" else None
        shift, src = await detect_shift(emp, wd, cin, cout, manual)
        late, early = minutes_for(shift, cin, cout)
        data = {"employee_id": emp["id"], "work_date": wd, "check_in_time": cin, "check_out_time": cout,
                "minutes_late": late, "minutes_early_leave": early, "is_missing_check_in": not cin,
                "is_missing_check_out": not cout, "leave_type": "present",
                "notes": str(_pick(r, "keterangan") or ""), "photo_in_url": _pick(r, "foto_masuk"),
                "photo_out_url": _pick(r, "foto_pulang"), "location_in": _pick(r, "lokasi_masuk"),
                "location_out": _pick(r, "lokasi_pulang"), "source": "rumatku_import", "updated_at": now_iso(),
                **shift_fields(shift, src)}
        key = data["shift_code"] or "LIBUR"
        shifts[key] = shifts.get(key, 0) + 1
        if existing:
            await db.attendance_daily_logs.update_one({"_id": existing["_id"]}, {"$set": data})
            updated += 1
        else:
            await db.attendance_daily_logs.insert_one({**data, "id": str(uuid.uuid4())})
            created += 1
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors, "shift_summary": shifts}
