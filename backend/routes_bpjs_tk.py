"""BPJS Ketenagakerjaan "data given": the JKK / JKM / JHT / JP amounts BPJS itself bills per person (Rincian Iuran, Formulir 2a PU),
imported by NIK. Used by engine.calc_bpjs when config BPJS_TK_BASIS = "import" (user 1 Nov 2026); people without a record keep the
formula. Manager HRD only, like the other tax / BPJS data."""
import csv
import difflib
import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from core import db, now_iso, require_manager, get_configs, csv_delimiter, actor
from routes_tax import _rows_from_upload, _num

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_manager)])

# import file columns (header names are case-insensitive); amounts in rupiah per month
COLUMNS = ["nik", "nama", "upah_tk", "jkk", "jkm", "jht_perusahaan", "jht_karyawan", "jp_dasar", "jp_perusahaan", "jp_karyawan"]
AMOUNTS = {"jkk": "jkk", "jkm": "jkm", "jht_perusahaan": "jht_company", "jht_karyawan": "jht_employee",
           "jp_dasar": "jp_base", "jp_perusahaan": "jp_company", "jp_karyawan": "jp_employee"}


def _name_key(s: str) -> str:
    return re.sub(r"[^a-z ]", "", re.sub(r",.*", "", (s or "").lower().replace(".", ""))).strip()


async def _latest_participants() -> list:
    """People in the newest period whose HAM template joins JHT or JP (what the import should cover)."""
    per = await db.payroll_periods.find_one({}, {"_id": 0, "employee_ids": 1, "start_date": 1}, sort=[("start_date", -1)])
    ids = (per or {}).get("employee_ids") or []
    out = []
    async for e in db.employees.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "nik": 1, "name": 1, "bpjs_programs": 1, "has_bpjs_tk": 1}):
        prog = e.get("bpjs_programs") or {}
        if any(prog.get(p, e.get("has_bpjs_tk", True)) for p in ("jht", "jp", "jkk", "jkm")):
            out.append(e)
    return out


@router.get("/bpjs-tk-given")
async def list_given():
    rows = await db.bpjs_tk_given.find({}, {"_id": 0}).to_list(5000)
    emps = {e["id"]: e async for e in db.employees.find({}, {"_id": 0, "id": 1, "nik": 1, "name": 1})}
    for r in rows:
        r["name"] = emps.get(r["employee_id"], {}).get("name")
    rows.sort(key=lambda r: r.get("nik") or "")
    have = {r["employee_id"] for r in rows}
    missing = [{"nik": e["nik"], "name": e["name"]} for e in await _latest_participants() if e["id"] not in have]
    cfg = await get_configs()
    return {"count": len(rows), "updated_at": max((r.get("updated_at") or "" for r in rows), default=None),
            "basis": cfg.get("BPJS_TK_BASIS"), "rows": rows, "participants_without_record": missing}


@router.get("/bpjs-tk-given/template")
async def template():
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=csv_delimiter(await get_configs()))
    w.writerow(COLUMNS)
    w.writerow(["2023040", "A. ZULFIANA TENRI LENGKA", 3000000, 7200, 9000, 111000, 60000, 3000000, 60000, 30000])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="template_bpjs_tk_given.csv"'})


@router.post("/bpjs-tk-given/import")
async def import_given(dry_run: bool = False, file: UploadFile = File(...), user: dict = Depends(require_manager)):
    """dry_run=true: read and validate only (preview). Otherwise upsert one record per NIK; people not in the file are untouched."""
    try:
        rows = _rows_from_upload(file.filename or "", await file.read())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"File tidak dapat dibaca: {e}")
    if rows and "nik" not in rows[0]:
        raise HTTPException(400, "Kolom 'nik' tidak ditemukan. Unduh template untuk melihat kolom yang dipakai")
    emps = {e["nik"]: e async for e in db.employees.find({}, {"_id": 0, "id": 1, "nik": 1, "name": 1})}
    imported, errors, warnings, seen, docs = 0, [], [], set(), []
    for i, r in enumerate(rows, start=2):
        nik = str(r.get("nik") or "").strip()
        if nik.endswith(".0"):
            nik = nik[:-2]
        e = emps.get(nik)
        if not e:
            errors.append(f"Baris {i}: NIK '{nik}' tidak ditemukan di RUSA")
            continue
        if nik in seen:
            errors.append(f"Baris {i}: NIK '{nik}' muncul dua kali di berkas")
            continue
        seen.add(nik)
        nama = str(r.get("nama") or "").strip()
        if nama and difflib.SequenceMatcher(None, _name_key(nama), _name_key(e["name"])).ratio() < 0.5:
            warnings.append(f"Baris {i}: nama di berkas '{nama}' jauh berbeda dari '{e['name']}' (NIK {nik}), periksa kecocokannya")
        try:
            vals = {dst: round(_num(r.get(src)), 2) for src, dst in AMOUNTS.items()}
            upah = round(_num(r.get("upah_tk")), 2)
        except ValueError as ex:
            errors.append(f"Baris {i}: angka tidak terbaca ({ex})")
            continue
        if any(v < 0 for v in [*vals.values(), upah]):
            errors.append(f"Baris {i}: angka tidak boleh negatif")
            continue
        docs.append({"employee_id": e["id"], "nik": nik, "upah_tk": upah, **vals})
        imported += 1
    if not dry_run:
        for d in docs:
            await db.bpjs_tk_given.update_one(
                {"employee_id": d["employee_id"]},
                {"$set": {**d, "updated_at": now_iso(), "imported_by": actor(user), "source": file.filename or ""},
                 "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    have = {d["employee_id"] for d in docs} | {r["employee_id"] async for r in db.bpjs_tk_given.find({}, {"_id": 0, "employee_id": 1})}
    missing = [{"nik": e["nik"], "name": e["name"]} for e in await _latest_participants() if e["id"] not in have]
    return {"dry_run": dry_run, "imported": imported, "errors": errors, "warnings": warnings,
            "participants_without_record": missing}
