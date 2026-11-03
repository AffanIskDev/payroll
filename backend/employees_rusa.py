"""Karyawan & gaji yang dikelola LANGSUNG di RUSA (user 3 Nov 2026) — untuk perusahaan yang belum punya sistem operasional
(ROSY/HAM), atau karyawan RUMAT yang gajinya memang diinput di RUSA.

Satu karyawan = satu sumber: `source: "rosy"` (dari HAM, hanya-baca di RUSA, diperbarui Fetch) atau `source: "rusa"` (diinput
di sini, TIDAK disentuh Fetch). Kuncinya NIK. Tahap 1: presensi dianggap hadir penuh (`attendance_exempt`), potongan presensi
menyusul lewat import rekap per periode (tahap 2).

Tiga jalan masuk, satu aturan validasi (`validate_row`): form Tambah/Ubah, dan import Excel (template → pratinjau → proses).
Hanya Manager HRD (data gaji)."""
import io
import re
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from core import actor, db, now_iso, require_manager
import integrations

router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_manager)])

PTKP_RE = re.compile(r"^(TK|K)/[0-3]$")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# (kunci, judul kolom, wajib, contoh) — urutan = urutan kolom template
COLUMNS = [
    ("nik", "NIK", True, "CONTOH-001"),
    ("name", "Nama", True, "Contoh Nama"),
    ("gender", "Jenis Kelamin (L/P)", True, "P"),
    ("birth_date", "Tgl Lahir (YYYY-MM-DD)", False, "1995-04-13"),
    ("email", "Email", False, "siti@perusahaan.co.id"),
    ("department", "Departemen", False, "Pelayanan"),
    ("position", "Jabatan", False, "Perawat"),
    ("employment_type", "Status Kepegawaian", False, "Tetap"),
    ("join_date", "Tgl Masuk (YYYY-MM-DD)", False, "2026-01-05"),
    ("exit_date", "Tgl Keluar (YYYY-MM-DD)", False, ""),
    ("ptkp_status", "PTKP", True, "TK/0"),
    ("npwp", "NPWP", False, ""),
    ("ktp", "No. KTP", False, ""),
    ("basic_salary", "Gaji Pokok", True, 3000000),
    ("position_allowance", "Tunj. Jabatan", False, 500000),
    ("monthly_attendance_allowance", "Tunj. Kehadiran", False, 1000000),
    ("overtime_hourly_rate", "Tarif Lembur per Jam", False, 0),
    ("bpjs_kes", "BPJS Kesehatan (Ya/Tidak)", False, "Ya"),
    ("bpjs_tk", "BPJS Ketenagakerjaan (Ya/Tidak)", False, "Ya"),
    ("bank_name", "Bank", False, "Bank Syariah Indonesia"),
    ("bank_code", "Kode Bank", False, "BSI"),
    ("bank_account_number", "No. Rekening", False, "7123456789"),
    ("bank_account_name", "Nama di Rekening", False, "Siti Aminah"),
    ("is_paid", "Status Gaji (Paid/Unpaid)", False, "Paid"),
    ("is_active", "Status (Aktif/Nonaktif)", False, "Aktif"),
]
LABEL = {k: t for k, t, _, _ in COLUMNS}
NUMERIC = ("basic_salary", "position_allowance", "monthly_attendance_allowance", "overtime_hourly_rate")
DATES = ("birth_date", "join_date", "exit_date")
# kolom yang dibandingkan untuk label "Ubah" di pratinjau
TRACKED = [k for k, *_ in COLUMNS]


# ------------------------------------------------------------------ nilai sel -> nilai bersih
def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _text(v) -> str:
    if _blank(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _number(v, label: str, errors: list) -> float:
    if _blank(v):
        return 0.0
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = re.sub(r"(?i)rp|\s", "", str(v))
        # "5.000.000" / "5,000,000" = ribuan; "2500000.50" = desimal
        s = re.sub(r"[.,](?=\d{3}(\D|$))", "", s)
        try:
            n = float(s.replace(",", "."))
        except ValueError:
            errors.append(f"{label} bukan angka: {v!r}")
            return 0.0
    if n < 0:
        errors.append(f"{label} tidak boleh negatif")
    return n


def _date(v, label: str, errors: list) -> Optional[str]:
    if _blank(v):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    errors.append(f"{label} harus berbentuk YYYY-MM-DD: {v!r}")
    return None


def _yes_no(v, label: str, errors: list, default: bool) -> bool:
    if _blank(v):
        return default
    s = str(v).strip().lower()
    if s in ("ya", "y", "yes", "true", "1", "ikut", "aktif", "paid"):
        return True
    if s in ("tidak", "t", "no", "n", "false", "0", "tidak ikut", "nonaktif", "unpaid"):
        return False
    errors.append(f"{label} harus Ya atau Tidak: {v!r}")
    return default


def validate_row(raw: dict) -> tuple:
    """raw: {kunci: nilai mentah}. Mengembalikan (data bersih, daftar galat). Data bersih memakai kunci COLUMNS."""
    e: list = []
    d = {k: raw.get(k) for k, *_ in COLUMNS}
    out = {
        "nik": _text(d["nik"]), "name": _text(d["name"]), "email": _text(d["email"]).lower(),
        "department": _text(d["department"]), "position": _text(d["position"]),
        "employment_type": _text(d["employment_type"]), "npwp": _text(d["npwp"]), "ktp": _text(d["ktp"]),
        "bank_name": _text(d["bank_name"]), "bank_code": _text(d["bank_code"]).upper(),
        "bank_account_number": re.sub(r"\s|-", "", _text(d["bank_account_number"])),
        "bank_account_name": _text(d["bank_account_name"]),
    }
    if not out["nik"]:
        e.append("NIK wajib diisi")
    elif out["nik"] in ("-", "0"):
        e.append("NIK tidak boleh '-' atau '0'")
    if not out["name"]:
        e.append("Nama wajib diisi")
    g = _text(d["gender"]).upper()[:1]
    if g not in ("L", "P"):
        e.append("Jenis Kelamin harus L atau P")
    out["gender"] = g or "L"
    ptkp = _text(d["ptkp_status"]).upper().replace(" ", "")
    if not PTKP_RE.match(ptkp):
        e.append("PTKP harus berbentuk TK/0 … TK/3 atau K/0 … K/3")
    out["ptkp_status"] = ptkp or "TK/0"
    for k in NUMERIC:
        out[k] = _number(d[k], LABEL[k], e)
    if not out["basic_salary"] > 0:
        e.append("Gaji Pokok wajib diisi (lebih dari 0)")
    for k in DATES:
        out[k] = _date(d[k], LABEL[k], e)
    if out["join_date"] and out["exit_date"] and out["exit_date"] < out["join_date"]:
        e.append("Tgl Keluar sebelum Tgl Masuk")
    out["bpjs_kes"] = _yes_no(d["bpjs_kes"], LABEL["bpjs_kes"], e, True)
    out["bpjs_tk"] = _yes_no(d["bpjs_tk"], LABEL["bpjs_tk"], e, True)
    out["is_paid"] = _yes_no(d["is_paid"], LABEL["is_paid"], e, True)
    out["is_active"] = _yes_no(d["is_active"], LABEL["is_active"], e, True)
    if out["bank_account_number"] and not out["bank_account_number"].isdigit():
        e.append("No. Rekening hanya boleh angka")
    if out["bank_account_number"] and not out["bank_account_name"]:
        e.append("Nama di Rekening wajib diisi bila No. Rekening diisi")
    return out, e


def to_employee_doc(row: dict) -> dict:
    """Baris bersih -> dokumen karyawan dengan kunci yang SAMA seperti hasil sinkron ROSY (integrations.normalize_employee),
    supaya mesin gaji tak membedakan sumbernya."""
    r = {
        "employee_id": row["nik"], "nik": row["nik"], "ktp": row["ktp"], "name": row["name"], "email": row["email"],
        "gender": row["gender"], "birth_date": row["birth_date"], "ptkp_status": row["ptkp_status"], "npwp": row["npwp"],
        "department": row["department"], "position": row["position"], "level": "",
        "employment_type": row["employment_type"], "is_active": row["is_active"], "join_date": row["join_date"],
        "exit_date": row["exit_date"], "is_paid": row["is_paid"], "attendance_exempt": True,
        "payroll_company_id": integrations.company_id(),
        "salary": {k: row[k] for k in NUMERIC},
        "bpjs": {"kes": row["bpjs_kes"], "jkk": row["bpjs_tk"], "jkm": row["bpjs_tk"], "jht": row["bpjs_tk"],
                 "jp": row["bpjs_tk"], "jkk_rate": 0.0024},
        "bank": {"name": row["bank_name"], "code": row["bank_code"], "account_number": row["bank_account_number"],
                 "account_name": row["bank_account_name"]},
        "data_issues": [],
    }
    doc = integrations.normalize_employee(r)
    doc.pop("rosy_employee_id", None)
    return doc


# Kunci yang TIDAK ditimpa saat mengubah karyawan RUSA: diatur di tempat lain / pilihan manual yang harus bertahan
KEEP_ON_UPDATE = ("prolonged_illness_month_count", "has_husband_certificate", "user_id_rumatku", "attendance_exempt",
                  "overtime_access", "data_issues", "payroll_company_id", "marital_status", "dependents_count")


def _view(emp: dict) -> dict:
    """Dokumen karyawan -> nilai tampilan seperti kolom template (untuk membandingkan & mengisi template)."""
    p = emp.get("bpjs_programs") or {}
    return {
        "nik": emp.get("nik") or "", "name": emp.get("name") or "", "gender": emp.get("gender") or "",
        "birth_date": emp.get("birth_date") or "", "email": emp.get("email") or "", "department": emp.get("department") or "",
        "position": emp.get("position") or "", "employment_type": emp.get("employment_type") or "",
        "join_date": emp.get("join_date") or "", "exit_date": emp.get("exit_date") or "",
        "ptkp_status": emp.get("ptkp_status") or "", "npwp": emp.get("npwp") or "", "ktp": emp.get("ktp") or "",
        "basic_salary": emp.get("basic_salary") or 0, "position_allowance": emp.get("position_allowance") or 0,
        "monthly_attendance_allowance": emp.get("monthly_attendance_allowance") or 0,
        "overtime_hourly_rate": emp.get("overtime_hourly_rate") or 0,
        "bpjs_kes": bool(emp.get("has_bpjs_kes")), "bpjs_tk": bool(emp.get("has_bpjs_tk") or any(p.get(x) for x in ("jkk", "jkm", "jht", "jp"))),
        "bank_name": emp.get("bank_name") or "", "bank_code": emp.get("bank_code") or "",
        "bank_account_number": emp.get("bank_account_number") or "", "bank_account_name": emp.get("bank_account_name") or "",
        "is_paid": emp.get("payroll_status") != "unpaid_leave", "is_active": emp.get("is_active") is not False,
    }


def changes(row: dict, existing: dict) -> list:
    old = _view(existing)
    out = []
    for k in TRACKED:
        a, b = row[k], old[k]
        if k in NUMERIC:
            same = float(a or 0) == float(b or 0)
        elif isinstance(a, bool) or isinstance(b, bool):
            same = bool(a) == bool(b)
        else:
            same = (a or "") == (b or "")
        if not same:
            out.append(LABEL[k])
    return out


# ------------------------------------------------------------------ simpan
async def save_row(row: dict, existing: Optional[dict], by: str) -> dict:
    doc = to_employee_doc(row)
    if existing:
        for k in KEEP_ON_UPDATE:
            doc.pop(k, None)
        # status payroll khusus (sakit berkepanjangan, kecelakaan kerja) bertahan selama baris tetap Paid
        if row["is_paid"] and existing.get("payroll_status") not in (None, "active", "unpaid_leave"):
            doc.pop("payroll_status", None)
        await db.employees.update_one({"id": existing["id"]}, {"$set": {**doc, "updated_at": now_iso(), "updated_by": by}})
        return {**existing, **doc}
    new = {**doc, "id": str(uuid.uuid4()), "source": "rusa", "payroll_company_id": integrations.company_id(),
           "attendance_exempt": True, "created_at": now_iso(), "created_by": by}
    await db.employees.insert_one({**new})
    return new


async def _nik_owner(nik: str, skip_id: Optional[str] = None) -> Optional[dict]:
    q = {"nik": nik}
    if skip_id:
        q["id"] = {"$ne": skip_id}
    return await db.employees.find_one(q, {"_id": 0, "id": 1, "source": 1, "name": 1})


def _conflict_msg(owner: dict) -> str:
    if (owner.get("source") or "rosy") != "rusa":
        return f"NIK sudah dipakai karyawan dari ROSY ({owner.get('name')}); datanya diubah di ROSY"
    return f"NIK sudah dipakai karyawan RUSA lain ({owner.get('name')})"


# ------------------------------------------------------------------ endpoint: satu karyawan
@router.post("/employees")
async def create_employee(body: dict = Body(...), user: dict = Depends(require_manager)):
    row, errs = validate_row(body)
    if not errs and (owner := await _nik_owner(row["nik"])):
        errs.append(_conflict_msg(owner))
    if errs:
        raise HTTPException(422, "; ".join(errs))
    return await save_row(row, None, actor(user))


@router.put("/employees/{eid}")
async def update_employee(eid: str, body: dict = Body(...), user: dict = Depends(require_manager)):
    emp = await db.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan")
    if emp.get("source") != "rusa":
        raise HTTPException(409, "Karyawan ini dikelola di ROSY; ubah datanya di ROSY lalu Fetch Data Terbaru")
    row, errs = validate_row(body)
    if not errs and (owner := await _nik_owner(row["nik"], eid)):
        errs.append(_conflict_msg(owner))
    if errs:
        raise HTTPException(422, "; ".join(errs))
    return await save_row(row, emp, actor(user))


@router.delete("/employees/{eid}")
async def delete_employee(eid: str):
    emp = await db.employees.find_one({"id": eid}, {"_id": 0, "source": 1})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan")
    if emp.get("source") != "rusa":
        raise HTTPException(409, "Karyawan dari ROSY tidak bisa dihapus di RUSA")
    if await db.payslips.count_documents({"employee_id": eid}):
        raise HTTPException(409, "Karyawan sudah punya slip gaji; nonaktifkan saja (Status Nonaktif + Tgl Keluar)")
    await db.employees.delete_one({"id": eid})
    return {"deleted": eid}


# ------------------------------------------------------------------ endpoint: import Excel
def build_template(existing: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Karyawan"
    head_fill = PatternFill("solid", fgColor="1F4E78")
    for j, (_, title, required, _) in enumerate(COLUMNS, 1):
        c = ws.cell(1, j, title + (" *" if required else ""))
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="B71C1C" if required else "1F4E78")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = max(14, min(32, len(title) + 4))
    ws.row_dimensions[1].height = 34
    if existing:
        for i, e in enumerate(existing, 2):
            v = _view(e)
            for j, (k, *_x) in enumerate(COLUMNS, 1):
                x = v[k]
                if k in ("bpjs_kes", "bpjs_tk"):
                    x = "Ya" if x else "Tidak"
                elif k == "is_paid":
                    x = "Paid" if x else "Unpaid"
                elif k == "is_active":
                    x = "Aktif" if x else "Nonaktif"
                ws.cell(i, j, x)
    else:
        for j, (_k, _t, _r, example) in enumerate(COLUMNS, 1):
            ws.cell(2, j, example).font = Font(italic=True, color="808080")
    for j, (k, *_x) in enumerate(COLUMNS, 1):
        for r in range(2, max(len(existing) + 2, 3)):
            ws.cell(r, j).number_format = "@" if k in ("nik", "npwp", "ktp", "bank_account_number") else (
                '#,##0' if k in NUMERIC else "General")
    ws.freeze_panes = "C2"
    guide = wb.create_sheet("Petunjuk")
    notes = [
        "Cara mengisi",
        "",
        "Kolom bertanda * (merah) wajib. Satu baris = satu karyawan; NIK adalah kuncinya.",
        "NIK yang sudah ada di RUSA akan DIUBAH; NIK baru akan DITAMBAH. Karyawan yang tidak ada di berkas tidak diubah/dihapus.",
        "NIK yang sudah dipakai karyawan dari ROSY ditolak (datanya diubah di ROSY).",
        "Tanggal: YYYY-MM-DD (mis. 2026-01-05). Angka: tanpa titik/koma ribuan (3000000).",
        "PTKP: TK/0 … TK/3 atau K/0 … K/3. Status Gaji: Paid atau Unpaid. Status: Aktif atau Nonaktif (isi Tgl Keluar bila nonaktif).",
        "BPJS Kesehatan / Ketenagakerjaan: Ya bila ikut. Ketenagakerjaan = JKK, JKM, JHT, dan JP.",
        "Presensi (tahap 1): karyawan RUSA dianggap hadir penuh; potongan presensi/alfa diinput lewat rekap per periode (menyusul).",
        "Sesudah diunggah & diproses, data masuk ke slip draft lewat \"Fetch Data Terbaru\" di halaman periode.",
    ]
    for i, t in enumerate(notes, 1):
        guide.cell(i, 1, t).alignment = Alignment(wrap_text=True, vertical="top")
    guide["A1"].font = Font(bold=True, size=13)
    guide.column_dimensions["A"].width = 130
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/employees/import/template")
async def import_template():
    """Template berisi karyawan RUSA saat ini (supaya ubah massal cukup edit lalu unggah); kosong = satu baris contoh."""
    existing = await db.employees.find({"source": "rusa"}, {"_id": 0}).sort("nik", 1).to_list(5000)
    return Response(build_template(existing), media_type=XLSX, headers={
        "Content-Disposition": 'attachment; filename="Template-Karyawan-Gaji-RUSA.xlsx"'})


def _parse_workbook(raw: bytes) -> list:
    """Baca sheet pertama: baris judul dikenali dari nama kolom (urutan bebas, tanda * diabaikan). -> [(no_baris, {kunci: nilai})]"""
    try:
        ws = load_workbook(io.BytesIO(raw), data_only=True).worksheets[0]
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Berkas bukan Excel (.xlsx) yang valid")
    by_title = {re.sub(r"\s*\*\s*$", "", t).strip().lower(): k for k, t, *_ in COLUMNS}
    rows = list(ws.iter_rows(values_only=True))
    header_at = next((i for i, r in enumerate(rows[:10]) if sum(1 for c in r if c and re.sub(r"\s*\*\s*$", "", str(c)).strip().lower() in by_title) >= 4), None)
    if header_at is None:
        raise HTTPException(400, "Baris judul tidak ditemukan. Pakai template dari tombol \"Unduh Template\".")
    cols = {j: by_title[re.sub(r"\s*\*\s*$", "", str(c)).strip().lower()] for j, c in enumerate(rows[header_at])
            if c and re.sub(r"\s*\*\s*$", "", str(c)).strip().lower() in by_title}
    missing = [LABEL[k] for k, _t, req, _x in COLUMNS if req and k not in cols.values()]
    if missing:
        raise HTTPException(400, "Kolom wajib tidak ada di berkas: " + ", ".join(missing))
    out = []
    for i, r in enumerate(rows[header_at + 1:], header_at + 2):
        d = {k: (r[j] if j < len(r) else None) for j, k in cols.items()}
        if all(_blank(v) for v in d.values()):
            continue
        # baris contoh bawaan template (huruf miring abu-abu, NIK "CONTOH-…") tidak ikut diproses
        if _text(d.get("nik")).upper().startswith("CONTOH"):
            continue
        out.append((i, d))
    if not out:
        raise HTTPException(400, "Tidak ada baris data di berkas")
    if len(out) > 3000:
        raise HTTPException(400, "Maksimal 3000 baris per berkas")
    return out


async def _plan(raw: bytes) -> list:
    """Pratinjau: tiap baris -> {row, nik, name, action: baru|ubah|sama|error, errors, changes, data}."""
    parsed = _parse_workbook(raw)
    existing = {e["nik"]: e async for e in db.employees.find({}, {"_id": 0})}
    seen: dict = {}
    plan = []
    for n, d in parsed:
        row, errs = validate_row(d)
        owner = existing.get(row["nik"])
        if row["nik"] and row["nik"] in seen:
            errs.append(f"NIK ganda di berkas (baris {seen[row['nik']]})")
        elif row["nik"]:
            seen[row["nik"]] = n
        if owner and (owner.get("source") or "rosy") != "rusa" and not errs:
            errs.append(_conflict_msg(owner))
        if errs:
            action, ch = "error", []
        elif owner:
            ch = changes(row, owner)
            action = "ubah" if ch else "sama"
        else:
            action, ch = "baru", []
        plan.append({"row": n, "nik": row["nik"], "name": row["name"], "action": action, "errors": errs, "changes": ch,
                     "data": row, "existing_id": (owner or {}).get("id")})
    return plan


def _summary(plan: list) -> dict:
    c = {a: sum(1 for p in plan if p["action"] == a) for a in ("baru", "ubah", "sama", "error")}
    c["total"] = len(plan)
    return c


@router.post("/employees/import/preview")
async def import_preview(file: UploadFile = File(...)):
    plan = await _plan(await file.read())
    return {"summary": _summary(plan), "rows": [{k: v for k, v in p.items() if k not in ("data", "existing_id")} for p in plan]}


@router.post("/employees/import/commit")
async def import_commit(file: UploadFile = File(...), user: dict = Depends(require_manager)):
    """Proses: hanya baris tanpa galat yang disimpan (baris Error dilewati dan dilaporkan)."""
    plan = await _plan(await file.read())
    by = actor(user)
    done = {"baru": 0, "ubah": 0}
    for p in plan:
        if p["action"] not in done:
            continue
        existing = await db.employees.find_one({"id": p["existing_id"]}, {"_id": 0}) if p["existing_id"] else None
        await save_row(p["data"], existing, by)
        done[p["action"]] += 1
    s = _summary(plan)
    await db.import_logs.insert_one({"id": str(uuid.uuid4()), "kind": "employees", "at": now_iso(), "by": by,
                                     "filename": file.filename, "summary": s, "saved": done})
    return {"summary": s, "saved": done, "skipped_errors": s["error"]}


# ------------------------------------------------------------------ untuk Fetch periode
async def rusa_employee_ids(start: str, end: str) -> list:
    """Karyawan RUSA yang ikut periode [start, end]: aktif dan masa kerjanya beririsan dengan periode."""
    ids = []
    async for e in db.employees.find({"source": "rusa"}, {"_id": 0, "id": 1, "is_active": 1, "join_date": 1, "exit_date": 1}):
        if e.get("join_date") and e["join_date"] > end:
            continue
        if e.get("exit_date") and e["exit_date"] < start:
            continue
        if e.get("is_active") is False and not e.get("exit_date"):
            continue
        ids.append(e["id"])
    return ids
