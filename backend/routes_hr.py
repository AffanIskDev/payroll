import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core import db, now_iso, require_hr, require_manager, hash_password, get_configs, DEFAULT_CONFIGS
from pipeline import (get_period, get_employee, period_logs, build_slip, recalc_and_save, process_period,
                      approve_slip, queue_delivery, ADJ_KEYS)
from pdf_service import render_payslip
import integrations

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])


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


@router.get("/integrations")
async def integration_status():
    return {s.lower(): {"mode": integrations.mode(s)} for s in ("ROSY", "RUMATKU")}


@router.get("/employees")
async def list_employees():
    return await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(2000)


async def sync_employees() -> list:
    """Fetch master karyawan & gaji dari ROSY; upsert by NIK. Returns employee ids."""
    try:
        rows = await integrations.fetch_employees()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data karyawan dari ROSY: {e}")
    ids = []
    for r in rows:
        existing = await db.employees.find_one({"nik": r["nik"]}, {"_id": 0, "id": 1})
        eid = existing["id"] if existing else str(uuid.uuid4())
        await db.employees.update_one({"nik": r["nik"]}, {"$set": {**r, "source": "rosy", "synced_at": now_iso()},
                                                         "$setOnInsert": {"id": eid, "created_at": now_iso()}},
                                      upsert=True)
        if r["email"] and not await db.users.find_one({"$or": [{"employee_id": eid}, {"email": r["email"]}]}):
            await db.users.insert_one({"id": str(uuid.uuid4()), "role": "employee", "employee_id": eid,
                                       "email": r["email"], "nik": r["nik"], "name": r["name"],
                                       "password_hash": hash_password(secrets.token_urlsafe(16)),
                                       "created_at": now_iso()})
        ids.append(eid)
    return ids


@router.get("/attendance")
async def list_attendance(employee_id: str, start: str, end: str):
    return await db.attendance_daily_logs.find(
        {"employee_id": employee_id, "work_date": {"$gte": start, "$lte": end}}, {"_id": 0}
    ).sort("work_date", 1).to_list(400)


@router.get("/periods")
async def list_periods():
    return await db.payroll_periods.find({}, {"_id": 0}).sort("start_date", -1).to_list(100)


@router.post("/periods")
async def create_period(body: PeriodIn):
    ids = await sync_employees()
    data = body.model_dump()
    data.update(id=str(uuid.uuid4()), status="draft", approved_by=None, approved_at=None, created_at=now_iso(),
                employee_ids=ids, employee_count=len(ids), employees_synced_at=now_iso(),
                employees_source=integrations.mode("ROSY"), attendance_synced_at=None)
    await db.payroll_periods.insert_one({**data})
    data.pop("_id", None)
    return data


@router.post("/periods/{pid}/fetch-attendance")
async def fetch_attendance(pid: str):
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci")
    q = {"id": {"$in": period["employee_ids"]}} if period.get("employee_ids") else {}
    emps = await db.employees.find(q, {"_id": 0}).to_list(5000)
    by_nik = {e["nik"]: e["id"] for e in emps}
    try:
        rows = await integrations.fetch_attendance(period["start_date"], period["end_date"], emps)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data absensi dari RUMATKU: {e}")
    await db.attendance_daily_logs.delete_many({"employee_id": {"$in": list(by_nik.values())},
                                                "work_date": {"$gte": period["start_date"], "$lte": period["end_date"]}})
    unknown, docs = set(), []
    for r in rows:
        nik = r.pop("nik")
        if nik not in by_nik or not (period["start_date"] <= r["work_date"] <= period["end_date"]):
            unknown.add(nik)
            continue
        docs.append({**r, "id": str(uuid.uuid4()), "employee_id": by_nik[nik], "source": "rumatku",
                     "synced_at": now_iso()})
    if docs:
        await db.attendance_daily_logs.insert_many(docs)
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "attendance_synced_at": now_iso(), "attendance_count": len(docs),
        "attendance_source": integrations.mode("RUMATKU")}})
    processed = await process_period(await get_period(pid))
    return {"logs": len(docs), "processed": processed, "unknown_niks": sorted(unknown)}


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


async def _locked(pid: str) -> dict:
    period = await get_period(pid)
    if period["status"] != "approved":
        raise HTTPException(400, "Slip dikirim ke Rumatku setelah seluruh periode di-approve & dikunci")
    return period


@router.post("/periods/{pid}/resend-failed")
async def resend_failed(pid: str):
    await _locked(pid)
    n = await queue_delivery(pid, {"delivery_status": "failed"}, attempts=1)
    if not n:
        raise HTTPException(400, "Tidak ada slip gagal kirim")
    return {"queued": n}


@router.post("/periods/{pid}/employees/{eid}/resend")
async def resend_one(pid: str, eid: str):
    await _locked(pid)
    slip = await _slip(pid, eid)
    if slip.get("delivery_status") == "sent":
        raise HTTPException(400, "Slip sudah terkirim ke Rumatku")
    if slip.get("delivery_status") == "queued":
        raise HTTPException(400, "Slip sedang dikirim")
    return {"queued": await queue_delivery(pid, {"employee_id": eid}, attempts=1)}


@router.get("/periods/{pid}/employees/{eid}/pdf")
async def preview_pdf(pid: str, eid: str):
    period = await get_period(pid)
    slip = await _slip(pid, eid)
    return Response(render_payslip(slip, period, await get_configs()), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="preview-{slip["employee"]["nik"]}.pdf"'})
