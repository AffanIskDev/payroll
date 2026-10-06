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


async def december_context(period: dict, emp: dict) -> Optional[dict]:
    if period["end_date"][5:7] != "12":
        return None
    year = int(period["end_date"][:4])
    init = await db.employee_tax_initial_balances.find_one({"employee_id": emp["id"], "tax_year": year}, {"_id": 0})
    cutoff = int((init or {}).get("cutoff_month") or 0)
    pids = {p["id"] async for p in db.payroll_periods.find(
        {"id": {"$ne": period["id"]}, "end_date": {"$gte": f"{year}-{cutoff + 1:02d}-01", "$lt": f"{year}-12-01"}},
        {"_id": 0, "id": 1})}
    slips = await db.payslips.find({"employee_id": emp["id"], "payroll_period_id": {"$in": list(pids)}},
                                   {"_id": 0, "taxable_gross": 1, "pph21_amount": 1, "bpjs": 1}).to_list(12)
    return {
        "tax_year": year, "has_initial_balance": bool(init), "initial_months": cutoff,
        "initial_gross": float((init or {}).get("gross_income_ytd") or 0),
        "initial_jht_jp": float((init or {}).get("employee_jht_jp_ytd") or 0),
        "initial_pph21": float((init or {}).get("pph21_paid_ytd") or 0),
        "system_gross": sum(s["taxable_gross"] for s in slips),
        "system_jht_jp": sum(s["bpjs"]["jht_employee"] + s["bpjs"]["jp_employee"] for s in slips),
        "system_pph21": sum(s["pph21_amount"] for s in slips), "system_months": len(slips),
    }


async def build_slip(period: dict, emp: dict, adj: dict, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or await get_configs()
    logs = await period_logs(emp["id"], period)
    calc = compute_payslip(emp, logs, cfg, adj, await december_context(period, emp))
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
