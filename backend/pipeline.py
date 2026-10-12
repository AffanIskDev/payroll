import asyncio
import uuid
from pathlib import Path
from typing import Optional
from fastapi import HTTPException

from core import db, now_iso, get_configs, actor
from engine import compute_payslip
from labels import position_allowance_label
from pdf_service import save_encrypted

ADJ_KEYS = ("overtime_hours", "kpi_incentive", "additional_bonus", "other_deductions")
EMP_SNAPSHOT = ("id", "nik", "name", "email", "department", "birth_date", "bank_name", "bank_code", "bank_account_number",
                "gender")


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


async def overtime_hours(period: dict, emp_id: str, logs: list) -> float:
    """HAM periods: approved claims paid in this period (pay month may differ from the claim date).
    Simulation: overtime recorded on the daily logs."""
    if period.get("overtime_source") == "ham":
        claims = await db.overtime_claims.find({"payroll_period_id": period["id"], "employee_id": emp_id},
                                               {"_id": 0, "menit_disetujui": 1}).to_list(1000)
        return sum(int(c["menit_disetujui"]) for c in claims) / 60
    return sum(float(lg.get("overtime_hours") or 0) for lg in logs)


async def period_components(period: dict, emp_id: str) -> dict:
    """ROSY's monthly components for this period (Tambahan Bulanan, integrations.MONTHLY_COMPONENTS), synced into
    period_components, as {kode: nominal}."""
    out = {}
    async for d in db.period_components.find({"payroll_period_id": period["id"], "employee_id": emp_id},
                                             {"_id": 0, "kode": 1, "nominal": 1}):
        out[d["kode"]] = out.get(d["kode"], 0) + float(d["nominal"])
    return out


async def build_slip(period: dict, emp: dict, adj: dict, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or await get_configs()
    logs = await period_logs(emp["id"], period)
    comp = await period_components(period, emp["id"])
    # Transport Homecare, Bonus, THR, Potongan Tidak Mencapai Target and Cicilan / Pinjaman come from ROSY only,
    # never from the review page
    adj = {**adj, "overtime_hours": await overtime_hours(period, emp["id"], logs),
           "transport_homecare": comp.get("TRANSPORT_HOMECARE", 0), "additional_bonus": comp.get("BONUS", 0),
           "thr": comp.get("THR", 0), "target_deduction": comp.get("TARGET_DEDUCTION", 0),
           "loan_installment": comp.get("LOAN_INSTALLMENT", 0)}
    calc = compute_payslip(emp, logs, cfg, adj, await december_context(period, emp))
    calc["employee"] = {k: emp.get(k) for k in EMP_SNAPSHOT}
    calc["position_allowance_label"] = position_allowance_label(emp)
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
    if not period.get("employee_ids"):
        return 0  # not synced yet: never fall back to every employee in the database
    async for emp in db.employees.find({"id": {"$in": period["employee_ids"]}}, {"_id": 0}):
        existing = await db.payslips.find_one({"payroll_period_id": period["id"], "employee_id": emp["id"]},
                                              {"_id": 0})
        adj = {k: (existing or {}).get(k, 0) for k in ADJ_KEYS}
        await recalc_and_save(period, emp, adj, cfg=cfg)
        count += 1
    return count


async def approve_slip(slip: dict, period: dict, user: dict) -> dict:
    path = save_encrypted(slip, period)
    upd = {"status": "approved", "pdf_path": path, "approved_by": actor(user), "approved_at": now_iso()}
    await db.payslips.update_one({"id": slip["id"]}, {"$set": upd})
    remaining = await db.payslips.count_documents({"payroll_period_id": period["id"], "status": {"$ne": "approved"}})
    if remaining == 0:
        await db.payroll_periods.update_one({"id": period["id"]}, {"$set": {
            "status": "approved", "approved_by": actor(user), "approved_at": now_iso()}})
        await queue_delivery(period["id"])
    return {**slip, **upd}


async def deliver_slip(slip: dict, period: dict, attempts: int = 3) -> str:
    path = slip.get("pdf_path")
    if not path or not Path(path).exists():
        path = save_encrypted(slip, period)
    import integrations
    upd, err, n = {}, "", 0
    for n in range(1, attempts + 1):
        try:
            res = await integrations.push_payslip(slip, period, path)
            upd = {"delivery_status": "sent", "delivered_at": now_iso(), "delivery_ref": res.get("ref"),
                   "delivery_error": None}
            break
        except Exception as e:  # noqa: BLE001
            err = str(e) or e.__class__.__name__
            if n < attempts:
                await asyncio.sleep(n)
    if not upd:
        upd = {"delivery_status": "failed", "delivery_error": err}
    upd.update(pdf_path=path, delivery_attempts=int(slip.get("delivery_attempts") or 0) + n,
               delivery_last_attempt_at=now_iso())
    await db.payslips.update_one({"id": slip["id"]}, {"$set": upd})
    return upd["delivery_status"]


async def _deliver_period(pid: str, attempts: int):
    period = await get_period(pid)
    async for s in db.payslips.find({"payroll_period_id": pid, "delivery_status": "queued"}, {"_id": 0}):
        await deliver_slip(s, period, attempts)
    sent = await db.payslips.count_documents({"payroll_period_id": pid, "delivery_status": "sent"})
    failed = await db.payslips.count_documents({"payroll_period_id": pid, "delivery_status": "failed"})
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "delivery_sent": sent, "delivery_failed": failed, "delivery_finished_at": now_iso()}})


async def queue_delivery(pid: str, query: Optional[dict] = None, attempts: int = 3) -> int:
    q = {"payroll_period_id": pid, "status": "approved", "delivery_status": {"$ne": "sent"}, **(query or {})}
    res = await db.payslips.update_many(q, {"$set": {"delivery_status": "queued"}})
    await db.payroll_periods.update_one({"id": pid}, {"$set": {"delivery_started_at": now_iso()}})
    asyncio.create_task(_deliver_period(pid, attempts))
    return res.modified_count
