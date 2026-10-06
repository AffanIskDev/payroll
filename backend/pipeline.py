import uuid
from typing import Optional
from fastapi import HTTPException

from core import db, now_iso, get_configs
from engine import compute_payslip
from pdf_service import save_encrypted

ADJ_KEYS = ("overtime_hours", "kpi_incentive", "additional_bonus", "late_penalty_compensation", "other_deductions")
EMP_SNAPSHOT = ("id", "nik", "name", "email", "department", "birth_date", "bank_name", "bank_account_number", "gender")


async def period_logs(emp_id: str, period: dict) -> list:
    return await db.attendance_daily_logs.find(
        {"employee_id": emp_id, "work_date": {"$gte": period["start_date"], "$lte": period["end_date"]}},
        {"_id": 0}).sort("work_date", 1).to_list(400)


async def get_period(pid: str) -> dict:
    p = await db.payroll_periods.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Periode tidak ditemukan")
    return p


async def get_employee(eid: str) -> dict:
    e = await db.employees.find_one({"id": eid}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Karyawan tidak ditemukan")
    return e


async def build_slip(period: dict, emp: dict, adj: dict, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or await get_configs()
    logs = await period_logs(emp["id"], period)
    calc = compute_payslip(emp, logs, cfg, adj)
    calc["employee"] = {k: emp.get(k) for k in EMP_SNAPSHOT}
    return calc


async def recalc_and_save(period: dict, emp: dict, adj: dict, notes: Optional[str] = None,
                          manual: bool = False, cfg: Optional[dict] = None) -> dict:
    existing = await db.payslips.find_one({"payroll_period_id": period["id"], "employee_id": emp["id"]}, {"_id": 0})
    if existing and existing.get("status") == "approved":
        return existing
    calc = await build_slip(period, emp, adj, cfg)
    doc = {**calc, "payroll_period_id": period["id"], "employee_id": emp["id"], "status": "draft",
           "is_manually_adjusted": manual or bool(existing and existing.get("is_manually_adjusted")),
           "adjustment_notes": notes if notes is not None else (existing or {}).get("adjustment_notes", ""),
           "updated_at": now_iso()}
    if existing:
        doc["id"] = existing["id"]
        await db.payslips.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = now_iso()
        await db.payslips.insert_one({**doc})
    return doc


async def process_period(period: dict) -> int:
    cfg = await get_configs()
    count = 0
    async for emp in db.employees.find({}, {"_id": 0}):
        existing = await db.payslips.find_one({"payroll_period_id": period["id"], "employee_id": emp["id"]},
                                              {"_id": 0})
        adj = {k: (existing or {}).get(k, 0) for k in ADJ_KEYS}
        await recalc_and_save(period, emp, adj, cfg=cfg)
        count += 1
    if period["status"] == "draft":
        await db.payroll_periods.update_one({"id": period["id"]}, {"$set": {"status": "pending_approval"}})
    return count


async def approve_slip(slip: dict, period: dict, user: dict) -> dict:
    path = save_encrypted(slip, period)
    upd = {"status": "approved", "pdf_path": path, "approved_by": user["email"], "approved_at": now_iso()}
    await db.payslips.update_one({"id": slip["id"]}, {"$set": upd})
    remaining = await db.payslips.count_documents({"payroll_period_id": period["id"], "status": {"$ne": "approved"}})
    if remaining == 0:
        await db.payroll_periods.update_one({"id": period["id"]}, {"$set": {
            "status": "approved", "approved_by": user["email"], "approved_at": now_iso()}})
    return {**slip, **upd}
