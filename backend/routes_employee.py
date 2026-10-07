from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from core import db, require_employee, get_configs
from pipeline import get_period
from pdf_service import save_encrypted, encrypt_pdf, birth_password
from tax_forms import list_1721a1, render_1721a1

router = APIRouter(prefix="/api/v1/employee")
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
        path = save_encrypted(slip, await get_period(slip["payroll_period_id"]), await get_configs())
        await db.payslips.update_one({"id": sid}, {"$set": {"pdf_path": path}})
    p = slip.get("payroll_period_id")
    period = await get_period(p)
    name = f"Slip-Gaji-{slip['employee']['nik']}-{period['period_name'].replace(' ', '-')}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=name)


async def _approved_years(eid: str) -> list:
    pids = [s["payroll_period_id"] async for s in db.payslips.find(
        {"employee_id": eid, "status": "approved"}, {"_id": 0, "payroll_period_id": 1})]
    years = {int(p["end_date"][:4]) async for p in db.payroll_periods.find({"id": {"$in": pids}}, {"_id": 0})}
    return sorted(years, reverse=True)


@router.get("/tax-forms/1721a1")
async def my_1721a1(user: dict = Depends(require_employee)):
    out = []
    for y in await _approved_years(user["employee_id"]):
        out += await list_1721a1(y, user["employee_id"])
    return out


@router.get("/tax-forms/1721a1/{year}/download")
async def my_1721a1_pdf(year: int, user: dict = Depends(require_employee)):
    if year not in await _approved_years(user["employee_id"]):
        raise HTTPException(404, "Bukti potong belum tersedia")
    f = (await list_1721a1(year, user["employee_id"]))[0]
    emp = await db.employees.find_one({"id": user["employee_id"]}, {"_id": 0, "birth_date": 1})
    data = encrypt_pdf(await render_1721a1(f), birth_password(emp["birth_date"]))
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="1721-A1_{f["nik"]}_{year}.pdf"'})


@router.get("/profile")
async def profile(user: dict = Depends(require_employee)):
    emp = await db.employees.find_one({"id": user["employee_id"]}, {"_id": 0})
    return {k: emp.get(k) for k in ("nik", "name", "email", "department", "bank_name", "bank_account_number",
                                    "payroll_status")}
