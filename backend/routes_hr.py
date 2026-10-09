import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core import db, now_iso, require_hr, require_manager, actor, DEFAULT_CONFIGS
from pipeline import (get_period, get_employee, period_logs, build_slip, recalc_and_save, process_period,
                      approve_slip, queue_delivery, ADJ_KEYS)
from pdf_service import render_payslip
from periods import payroll_month, period_name_for, validate_dates, overlaps
import integrations

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_hr)])


class PeriodIn(BaseModel):
    period_name: Optional[str] = None  # ignored when the period lies within one month (auto "Oktober 2026")
    start_date: str
    end_date: str
    payment_date: Optional[str] = None


class AdjustIn(BaseModel):
    overtime_hours: float = 0
    kpi_incentive: float = 0
    additional_bonus: float = 0
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
             "by": (p.get("submitted_by_name") or p.get("submitted_by")) if kind == "submitted"
             else (p.get("rejected_by_name") or p.get("rejected_by")),
             "at": p.get("submitted_at") if kind == "submitted" else p.get("rejected_at"),
             "reason": p.get("rejection_reason") if kind == "rejected" else None} for p in periods]


@router.get("/configs")
async def list_configs():
    return await db.payroll_configs.find({}, {"_id": 0}).sort("config_key", 1).to_list(100)


@router.put("/configs", dependencies=[Depends(require_manager)])
async def update_configs(body: dict):
    for k, v in body.items():
        if k not in DEFAULT_CONFIGS:
            raise HTTPException(400, f"Config tidak dikenal: {k}")
        if k == "CSV_DELIMITER" and str(v) not in (",", ";", "|", "tab"):
            raise HTTPException(400, "Pemisah CSV harus , ; | atau tab")
        await db.payroll_configs.update_one({"config_key": k}, {"$set": {"config_value": str(v)}})
    return await list_configs()


@router.get("/employees")
async def list_employees():
    return await db.employees.find({}, {"_id": 0}).sort("nik", 1).to_list(2000)


async def sync_employees(periode: str) -> tuple:
    """Fetch master karyawan & gaji dari ROSY (HAM); upsert by rosy_employee_id. Returns (employee ids, meta).

    HAM's nik is not unique, so it is never the key. Employees created before rosy_employee_id existed
    are adopted once by nik."""
    try:
        rows, meta = await integrations.fetch_employees(periode)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data karyawan dari ROSY: {e}")
    ids = []
    for r in rows:
        existing = await db.employees.find_one({"rosy_employee_id": r["rosy_employee_id"]}, {"_id": 0, "id": 1}) or \
            await db.employees.find_one({"rosy_employee_id": {"$exists": False}, "nik": r["nik"]}, {"_id": 0, "id": 1})
        eid = existing["id"] if existing else str(uuid.uuid4())
        await db.employees.update_one({"id": eid}, {"$set": {**r, "source": "rosy", "in_rosy": True,
                                                            "synced_at": now_iso()},
                                                   "$setOnInsert": {"created_at": now_iso()}}, upsert=True)
        ids.append(eid)
    # Employees ROSY no longer returns (resigned, moved company, lost their salary contract) stay for history
    # but are flagged, so the list never silently mixes them with the current payroll population
    gone = await db.employees.update_many(
        {"source": "rosy", "rosy_employee_id": {"$nin": [r["rosy_employee_id"] for r in rows]}},
        {"$set": {"in_rosy": False}})
    await db.sync_status.update_one({"key": "employees"}, {"$set": {
        "key": "employees", "synced_at": now_iso(), "periode": periode, "source": integrations.mode("ROSY"),
        "count": len(ids), "skipped": meta.get("dilewati") or [], "company": meta.get("company"),
        "not_in_rosy": await db.employees.count_documents({"source": "rosy", "in_rosy": False}),
        "newly_not_in_rosy": gone.modified_count,
        "data_issues": dict(Counter(i for r in rows for i in r.get("data_issues") or []))}}, upsert=True)
    return ids, meta


@router.get("/employees/sync-status")
async def employees_sync_status():
    return await db.sync_status.find_one({"key": "employees"}, {"_id": 0}) or {}


@router.post("/employees/sync")
async def sync_employees_now(periode: Optional[str] = None):
    """Manual sync from the Karyawan menu; defaults to the current month (WIB)."""
    periode = periode or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periode):
        raise HTTPException(400, "Format periode harus YYYY-MM")
    await sync_employees(periode)
    return await employees_sync_status()


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
    """Creates the period and immediately syncs everything from ROSY, so the slips are there at once.
    One period per month (ROSY pays 1 slip per employee per month); dates may not overlap another period."""
    validate_dates(body.start_date, body.end_date)
    name = period_name_for(body.start_date, body.end_date) or (body.period_name or "").strip()
    if not name:
        raise HTTPException(400, "Periode lintas bulan wajib diberi nama")
    bulan = payroll_month(body.start_date)
    async for other in db.payroll_periods.find({}, {"_id": 0, "period_name": 1, "bulan": 1, "start_date": 1,
                                                    "end_date": 1}):
        if other.get("bulan") == bulan:
            raise HTTPException(409, f"Periode {other['period_name']} sudah ada — satu bulan hanya satu periode")
        if overlaps(body.start_date, body.end_date, other):
            raise HTTPException(409, f"Tanggal bertumpuk dengan periode {other['period_name']}")
    data = body.model_dump()
    data.update(id=str(uuid.uuid4()), period_name=name, bulan=bulan, status="draft", approved_by=None,
                approved_at=None, created_at=now_iso(), employee_ids=[], employee_count=0, attendance_synced_at=None)
    try:
        await db.payroll_periods.insert_one({**data})
    except DuplicateKeyError:
        raise HTTPException(409, f"Periode {name} sudah ada — satu bulan hanya satu periode")
    try:
        result = await sync_period(data["id"])
    except HTTPException as e:
        # the draft stays; "Sinkron dari ROSY" retries
        return {**await get_period(data["id"]), "sync_error": e.detail}
    return {**await get_period(data["id"]), "sync": result}


SYNC_STALE = timedelta(minutes=10)


@router.post("/periods/{pid}/fetch-attendance")
async def sync_now(pid: str):
    """Button "Sinkron dari ROSY": employees & salary, attendance, overtime and Transport Homecare."""
    return await sync_period(pid)


async def sync_period(pid: str) -> dict:
    period = await get_period(pid)
    if period["status"] not in EDITABLE_STATUSES:
        raise HTTPException(400, "Periode sedang direview Manager atau sudah dikunci")
    now = datetime.now(timezone.utc)
    lock = await db.payroll_periods.update_one(
        {"id": pid, "$or": [{"sync_running_since": None}, {"sync_running_since": {"$exists": False}},
                            {"sync_running_since": {"$lt": (now - SYNC_STALE).isoformat()}}]},
        {"$set": {"sync_running_since": now.isoformat()}})
    if not lock.modified_count:
        raise HTTPException(409, "Sinkron periode ini sedang berjalan. Tunggu sebentar lalu muat ulang")
    try:
        result = await _sync(pid)
    except HTTPException as e:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"last_sync_error": e.detail, "last_sync_at": now_iso()}})
        raise
    finally:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"sync_running_since": None}})
    await db.payroll_periods.update_one({"id": pid}, {"$set": {"last_sync_at": now_iso()}, "$unset": {"last_sync_error": ""}})
    return result


async def _sync(pid: str) -> dict:
    period = await get_period(pid)
    # One button pulls everything fresh from ROSY: salary, overtime rate and population can change in HAM
    # after the period was created (e.g. HRD fills in an overtime rate), and the slips must follow
    ids, emp_meta = await sync_employees(payroll_month(period["start_date"]))
    q = {"id": {"$in": ids}}
    emps = await db.employees.find(q, {"_id": 0}).to_list(5000)
    by_rosy = {e["rosy_employee_id"]: e["id"] for e in emps if e.get("rosy_employee_id")}
    by_nik = {e["nik"]: e["id"] for e in emps}
    # every HAM read happens before anything of this period is deleted
    try:
        rows, meta = await integrations.fetch_attendance(period["start_date"], period["end_date"], emps)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data absensi dari RUMATKU: {e}")
    try:
        overtime = await integrations.fetch_overtime(payroll_month(period["start_date"]))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gagal mengambil data lembur dari ROSY: {e}")
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "employee_ids": ids, "employee_count": len(ids), "employees_synced_at": now_iso(),
        "employees_source": integrations.mode("ROSY"), "employees_skipped": emp_meta.get("dilewati") or [],
        "company": emp_meta.get("company"),
        # slip signer = ROSY's payroll Document Signer for this company (same as ROSY's own slips)
        "signer": emp_meta.get("penandatangan")}})
    # draft slips of people who dropped out of the population (resigned, no salary contract) must not linger
    await db.payslips.delete_many({"payroll_period_id": pid, "employee_id": {"$nin": ids}, "status": {"$ne": "approved"}})
    # Transport Homecare (ROSY Tambahan Bulanan "Transport Rumat Kita") for this month
    comp_docs = [{"id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": by_rosy[rid],
                  "kode": "TRANSPORT_HOMECARE", "component_id": integrations.TRANSPORT_COMPONENT,
                  "nominal": nominal, "synced_at": now_iso()}
                 for rid, nominal in (emp_meta.get("transport") or {}).items() if rid in by_rosy]
    await db.period_components.delete_many({"payroll_period_id": pid})
    if comp_docs:
        await db.period_components.insert_many(comp_docs)
    await db.attendance_daily_logs.delete_many({"employee_id": {"$in": [e["id"] for e in emps]},
                                                "work_date": {"$gte": period["start_date"], "$lte": period["end_date"]}})
    # Approved overtime claims paid in this period (live only): the slip uses these, the daily log only shows them
    claim_docs, claim_minutes = [], {}
    if overtime is not None:
        claims, ot_meta = overtime
        for c in claims:
            eid = by_rosy.get(c["rosy_employee_id"])
            if not eid:
                continue
            claim_docs.append({**c, "id": str(uuid.uuid4()), "payroll_period_id": pid, "employee_id": eid,
                               "synced_at": now_iso()})
            claim_minutes[(eid, c["tanggal"])] = claim_minutes.get((eid, c["tanggal"]), 0) + c["menit_disetujui"]
        await db.overtime_claims.delete_many({"payroll_period_id": pid})
        if claim_docs:
            await db.overtime_claims.insert_many(claim_docs)
    unknown, docs = set(), []
    for r in rows:
        key = r.pop("rosy_employee_id", None)
        nik = r.pop("nik", None)
        eid = by_rosy.get(key) if key else by_nik.get(nik)
        if not eid or not (period["start_date"] <= r["work_date"] <= period["end_date"]):
            unknown.add(key or nik)
            continue
        if (eid, r["work_date"]) in claim_minutes:
            r["overtime_hours"] = claim_minutes[(eid, r["work_date"])] / 60
        docs.append({**r, "id": str(uuid.uuid4()), "employee_id": eid, "source": "rumatku",
                     "synced_at": now_iso()})
    if docs:
        await db.attendance_daily_logs.insert_many(docs)
    if overtime is not None:
        await db.payroll_periods.update_one({"id": pid}, {"$set": {"overtime_source": "ham", "overtime_summary": {
            "periode_bayar": ot_meta.get("periode_bayar"), "claims": len(claim_docs),
            "employees": len({d["employee_id"] for d in claim_docs}),
            "minutes": sum(d["menit_disetujui"] for d in claim_docs), "pending": ot_meta.get("menunggu", 0),
            "without_rate": ot_meta.get("tanpa_tarif") or []}}})
    # Without attendance rows an employee keeps the full attendance allowance — report them, never drop silently
    unlinked = meta.get("unlinked") or []
    unlinked_ids = {u.get("employee_id") for u in unlinked}
    logged = {d["employee_id"] for d in docs}
    missing = [{"employee_id": e["id"], "nik": e["nik"], "name": e["name"]} for e in emps
               if e["id"] not in logged and not e.get("attendance_exempt")
               and e.get("rosy_employee_id") not in unlinked_ids]
    await db.payroll_periods.update_one({"id": pid}, {"$set": {
        "attendance_synced_at": now_iso(), "attendance_count": len(docs),
        "attendance_source": integrations.mode("RUMATKU"), "attendance_unlinked": unlinked,
        "attendance_missing": missing, "attendance_unknown": sorted(unknown),
        "components_summary": {"transport_employees": len(comp_docs),
                               "transport_total": sum(d["nominal"] for d in comp_docs)}}})
    processed = await process_period(await get_period(pid))
    return {"logs": len(docs), "processed": processed, "unknown_niks": sorted(unknown),
            "unlinked": unlinked, "missing": missing, "transport_employees": len(comp_docs)}


@router.get("/periods/{pid}")
async def period_detail(pid: str):
    period = await get_period(pid)
    slips = await db.payslips.find({"payroll_period_id": pid}, {"_id": 0, "bpjs": 0}) \
        .sort("employee.nik", 1).to_list(2000)
    for s in slips:
        # slips calculated before Poin Absensi existed keep their absence days in the discipline breakdown
        disc = s.pop("discipline", None) or {}
        s.setdefault("absence_points", disc.get("attendance_cut_days", 0))
    return {"period": period, "payslips": slips}


@router.delete("/periods/{pid}")
async def delete_period(pid: str, user: dict = Depends(require_hr)):
    period = await get_period(pid)
    manager = user["role"] == "manager_hrd"
    if period["status"] == "pending_approval" and not manager:
        raise HTTPException(403, "Periode yang sudah diajukan hanya dapat dihapus Manager HRD")
    if period["status"] not in EDITABLE_STATUSES + ("pending_approval",) or \
            await db.payslips.count_documents({"payroll_period_id": pid, "status": "approved"}):
        raise HTTPException(400, "Hanya periode yang belum memiliki slip approved yang dapat dihapus")
    res = await db.payslips.delete_many({"payroll_period_id": pid})
    await db.overtime_claims.delete_many({"payroll_period_id": pid})
    await db.period_components.delete_many({"payroll_period_id": pid})
    await db.payroll_periods.delete_one({"id": pid})
    return {"ok": True, "deleted_payslips": res.deleted_count}


EDITABLE_STATUSES = ("draft", "revision")


async def _log(pid: str, action: str, user: dict, reason: str = "", extra: Optional[dict] = None):
    entry = {"action": action, "by": actor(user), "by_name": user.get("name"), "at": now_iso(), "reason": reason}
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
    if period.get("last_sync_error") or not period.get("attendance_synced_at"):
        raise HTTPException(400, "Sinkron dari ROSY belum berhasil. Klik \"Sinkron dari ROSY\" sebelum mengajukan")
    if not await db.payslips.count_documents({"payroll_period_id": pid}):
        raise HTTPException(400, "Belum ada slip. Jalankan proses payroll terlebih dahulu")
    await _log(pid, "submitted", user, extra={"status": "pending_approval", "submitted_by": actor(user),
                                              "submitted_by_name": user.get("name"), "submitted_at": now_iso()})
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
                                               "rejected_by": actor(user), "rejected_by_name": user.get("name"),
                                               "rejected_at": now_iso()})
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


@router.post("/periods/{pid}/resend-failed", dependencies=[Depends(require_manager)])
async def resend_failed(pid: str):
    await _locked(pid)
    n = await queue_delivery(pid, {"delivery_status": "failed"}, attempts=1)
    if not n:
        raise HTTPException(400, "Tidak ada slip gagal kirim")
    return {"queued": n}


@router.post("/periods/{pid}/employees/{eid}/resend", dependencies=[Depends(require_manager)])
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
    return Response(render_payslip(slip, period), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="preview-{slip["employee"]["nik"]}.pdf"'})
