from datetime import date, timedelta
from typing import Optional

from core import db

DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _days(weekday: tuple, half: Optional[tuple] = None, half_day: int = 5) -> dict:
    d = {str(i): {"start": weekday[0], "end": weekday[1]} for i in range(5)}
    if half:
        d[str(half_day)] = {"start": half[0], "end": half[1]}
    return d


DEFAULT_SCHEDULES = [
    {"code": "KANTOR_PUSAT", "name": "Kantor Pusat / Unit 1 Shift (Sen–Jum + Sabtu ½ hari)",
     "shifts": [{"code": "REG", "name": "Reguler", "days": _days(("08:00", "16:00"), ("08:00", "14:00"))}]},
    {"code": "UNIT_2SHIFT", "name": "Unit 2 Shift (Sen–Jum + Sabtu ½ hari)",
     "shifts": [{"code": "S1", "name": "Shift 1", "days": _days(("07:00", "15:00"), ("07:00", "13:00"))},
                {"code": "S2", "name": "Shift 2", "days": _days(("13:00", "21:00"), ("13:00", "19:00"))}]},
    {"code": "UNIT_MINGGU", "name": "Unit Khusus (Sen–Jum + Minggu ½ hari)",
     "shifts": [{"code": "REG", "name": "Reguler", "days": _days(("08:00", "16:00"), ("08:00", "14:00"), 6)}]},
]


def to_min(t: str) -> int:
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


async def seed_schedules():
    for s in DEFAULT_SCHEDULES:
        await db.work_schedules.update_one({"code": s["code"]}, {"$setOnInsert": s}, upsert=True)


async def employee_schedule(emp: dict) -> dict:
    code = emp.get("work_schedule_code") or "KANTOR_PUSAT"
    return await db.work_schedules.find_one({"code": code}, {"_id": 0})


def resolve_shift(schedule: dict, work_date: str, check_in: Optional[str], check_out: Optional[str],
                  shift_code: Optional[str] = None) -> Optional[dict]:
    """Return {code, name, start, end} for the day, or None if libur."""
    wd = str(date.fromisoformat(work_date).weekday())
    options = [{"code": s["code"], "name": s["name"], **s["days"][wd]}
               for s in schedule["shifts"] if s["days"].get(wd, {}).get("start")]
    if not options:
        return None
    if shift_code:
        match = [o for o in options if o["code"] == shift_code]
        if match:
            return match[0]
    if check_in:
        return min(options, key=lambda o: abs(to_min(o["start"]) - to_min(check_in)))
    if check_out:
        return min(options, key=lambda o: abs(to_min(o["end"]) - to_min(check_out)))
    return options[0]


def minutes_for(shift: Optional[dict], check_in: Optional[str], check_out: Optional[str]) -> tuple:
    if not shift:
        return 0, 0
    late = max(0, to_min(check_in) - to_min(shift["start"])) if check_in else 0
    early = max(0, to_min(shift["end"]) - to_min(check_out)) if check_out else 0
    return late, early


def week_start(work_date: str) -> str:
    d = date.fromisoformat(work_date)
    return (d - timedelta(days=d.weekday())).isoformat()


async def detect_shift(emp: dict, work_date: str, check_in: Optional[str], check_out: Optional[str],
                       manual: Optional[str] = None) -> tuple:
    """Priority: manual HRD choice > weekly rotation > nearest check-in."""
    sched = await employee_schedule(emp)
    source, code = ("manual", manual) if manual else ("auto", None)
    if not code:
        rot = await db.shift_rotations.find_one({"employee_id": emp["id"], "week_start": week_start(work_date)})
        if rot:
            source, code = "rotation", rot["shift_code"]
    shift = resolve_shift(sched, work_date, check_in, check_out, code)
    return shift, (source if shift and (not code or shift["code"] == code) else "auto")


def shift_fields(shift: Optional[dict], source: str = "auto") -> dict:
    return {"shift_code": shift and shift["code"], "shift_name": shift and shift["name"],
            "schedule_start": shift and shift["start"], "schedule_end": shift and shift["end"],
            "is_off_day": shift is None, "shift_source": source if shift else None}
