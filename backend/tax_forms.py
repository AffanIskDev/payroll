import io
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core import db, get_configs
from engine import annual_tax_summary, resolve_ptkp
from pdf_service import rp, NAVY

ITEM_LABELS = [
    ("i1", "1. Gaji / Pensiun atau THT/JHT"), ("i2", "2. Tunjangan PPh"),
    ("i3", "3. Tunjangan lainnya, uang lembur, dan sebagainya"), ("i4", "4. Honorarium dan imbalan lain sejenisnya"),
    ("i5", "5. Premi asuransi yang dibayar pemberi kerja"), ("i6", "6. Penerimaan dalam bentuk natura"),
    ("i7", "7. Tantiem, bonus, gratifikasi, jasa produksi dan THR"), ("i7a", "7a. Saldo awal YTD (impor sistem lama)"),
    ("i8", "8. JUMLAH PENGHASILAN BRUTO (1 s.d. 7a)"), ("i9", "9. Biaya jabatan"),
    ("i10", "10. Iuran terkait pensiun / JHT / JP (pekerja)"), ("i11", "11. JUMLAH PENGURANGAN (9 + 10)"),
    ("i12", "12. Jumlah penghasilan neto (8 - 11)"), ("i13", "13. Penghasilan neto masa sebelumnya"),
    ("i14", "14. Penghasilan neto setahun / disetahunkan"), ("i15", "15. Penghasilan Tidak Kena Pajak (PTKP)"),
    ("i16", "16. Penghasilan Kena Pajak setahun (14 - 15)"), ("i17", "17. PPh 21 atas PKP setahun (Pasal 17)"),
    ("i18", "18. PPh 21 yang telah dipotong masa sebelumnya"), ("i19", "19. PPh 21 terutang"),
    ("i20", "20. PPh 21 yang telah dipotong dan dilunasi"),
]


def _kept(s: dict, key: str) -> float:
    """A cut of the slip that still counts as income on the form: a slip taxed on the gross basis (PPH21_BASIS = kotor)
    kept Potongan Presensi & Absensi inside its PPh 21 base, so angka 1 / 3 must report them too — otherwise the
    form's annual tax would not match the PPh 21 actually withheld. Slips without the field (before the setting) = 0."""
    return s.get(key, 0) if s.get("pph21_basis") == "kotor" else 0


async def build_1721a1(emp: dict, year: int, seq: int) -> Optional[dict]:
    pids = {p["id"]: p async for p in db.payroll_periods.find(
        {"end_date": {"$gte": f"{year}-01-01", "$lte": f"{year}-12-31"}}, {"_id": 0})}
    init = await db.employee_tax_initial_balances.find_one({"employee_id": emp["id"], "tax_year": year}, {"_id": 0})
    cutoff = int((init or {}).get("cutoff_month") or 0)
    slips = [s async for s in db.payslips.find(
        {"employee_id": emp["id"], "status": "approved", "payroll_period_id": {"$in": list(pids)}}, {"_id": 0})]
    slips = [s for s in slips if int(pids[s["payroll_period_id"]]["end_date"][5:7]) > cutoff]
    if not slips and not init:
        return None
    months = sorted(int(pids[s["payroll_period_id"]]["end_date"][5:7]) for s in slips)
    sm = lambda f: sum(f(s) for s in slips)  # noqa: E731
    it = {
        "i1": sm(lambda s: s["basic_salary"] - s["absent_deduction_amount"] + _kept(s, "absent_deduction_amount")),
        "i2": 0,
        # tunjangan lainnya: jabatan net of the alfa/izin cut, attendance net of Potongan Presensi & Absensi, overtime,
        # Transport Homecare (.get: slips approved before these fields existed); cuts kept on kotor slips, see _kept
        "i3": sm(lambda s: s["position_allowance"] - s.get("position_deduction_amount", 0)
                 + _kept(s, "position_deduction_amount") + s["attendance_allowance"]
                 + _kept(s, "presence_penalty_amount") + _kept(s, "absence_penalty_amount")
                 + s["overtime_pay"] + s.get("transport_homecare", 0)), "i4": 0,
        "i5": sm(lambda s: s["tunjangan_bpjs_kes"] + s["bpjs"]["jkk"] + s["bpjs"]["jkm"]), "i6": 0,
        # angka 7 = "Tantiem, Bonus, Gratifikasi, Jasa Produksi dan THR" (THR dari ROSY sejak 12 Okt 2026)
        "i7": sm(lambda s: s["kpi_incentive"] + s["additional_bonus"] + s.get("thr", 0)),
        "i7a": float((init or {}).get("gross_income_ytd") or 0),
    }
    it["i8"] = sum(it[k] for k in ("i1", "i2", "i3", "i4", "i5", "i6", "i7", "i7a"))
    it["i10"] = float((init or {}).get("employee_jht_jp_ytd") or 0) + \
        sm(lambda s: s["bpjs"]["jht_employee"] + s["bpjs"]["jp_employee"])
    ptkp = resolve_ptkp(emp)
    worked = cutoff + len(slips)
    t = annual_tax_summary(it["i8"], it["i10"], worked, ptkp)
    it.update(i9=t["biaya_jabatan"], i11=t["biaya_jabatan"] + it["i10"], i12=t["neto_year"], i13=0,
              i14=t["neto_year"], i15=t["ptkp_amount"], i16=t["pkp"], i17=t["annual_tax"], i18=0,
              i19=t["annual_tax"], i20=float((init or {}).get("pph21_paid_ytd") or 0) + sm(lambda s: s["pph21_amount"]))
    start = 1 if init else (months[0] if months else 1)
    end = months[-1] if months else cutoff
    return {
        "employee_id": emp["id"], "nik": emp["nik"], "name": emp["name"], "npwp": emp.get("npwp") or "",
        "department": emp.get("department") or "", "gender": emp.get("gender"), "ptkp_status": ptkp,
        "tax_year": year, "masa_start": start, "masa_end": end, "months_worked": worked,
        "is_complete": end == 12, "has_initial_balance": bool(init),
        "number": f"1.1-{end:02d}.{str(year)[2:]}-{seq:07d}", "items": it,
        "difference": it["i19"] - it["i20"],
    }


async def list_1721a1(year: int, employee_id: Optional[str] = None) -> list:
    q = {"id": employee_id} if employee_id else {}
    emps = await db.employees.find(q, {"_id": 0}).sort("nik", 1).to_list(5000)
    all_emps = await db.employees.find({}, {"_id": 0, "id": 1}).sort("nik", 1).to_list(5000)
    seq = {e["id"]: i + 1 for i, e in enumerate(all_emps)}
    out = []
    for e in emps:
        f = await build_1721a1(e, year, seq[e["id"]])
        if f:
            out.append(f)
    return out


def _kv(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t


async def render_1721a1(f: dict) -> bytes:
    cfg = await get_configs()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=7.5, leading=9.5)
    head = Table([[Paragraph("<b>FORMULIR 1721 - A1</b><br/>BUKTI PEMOTONGAN PAJAK PENGHASILAN PASAL 21 BAGI "
                             "PEGAWAI TETAP ATAU PENERIMA PENSIUN BERKALA", ParagraphStyle(
                                 "h", parent=ss["Normal"], fontSize=10, leading=13, textColor=colors.white)),
                   Paragraph(f"<b>Nomor:</b> {f['number']}<br/><b>Masa Perolehan:</b> "
                             f"{f['masa_start']:02d} - {f['masa_end']:02d} / {f['tax_year']}",
                             ParagraphStyle("h2", parent=ss["Normal"], fontSize=8, leading=11, textColor=colors.white))]],
                 colWidths=[120 * mm, 62 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    els = [head, Spacer(1, 6),
           _kv([["NPWP Pemotong", cfg.get("COMPANY_NPWP", "-"), "Nama Pemotong", cfg.get("COMPANY_NAME", "-")],
                ["Alamat", cfg.get("COMPANY_ADDRESS", "-"), "", ""]],
               [28 * mm, 63 * mm, 28 * mm, 63 * mm]), Spacer(1, 6),
           Paragraph("<b>A. IDENTITAS PENERIMA PENGHASILAN YANG DIPOTONG</b>", small), Spacer(1, 2),
           _kv([["NPWP", f["npwp"] or "-", "NIK Karyawan", f["nik"]],
                ["Nama", f["name"], "Jenis Kelamin", "Laki-laki" if f["gender"] == "L" else "Perempuan"],
                ["Status PTKP", f["ptkp_status"], "Jabatan", f["department"] or "-"]],
               [28 * mm, 63 * mm, 28 * mm, 63 * mm]), Spacer(1, 6),
           Paragraph("<b>B. RINCIAN PENGHASILAN DAN PENGHITUNGAN PPh PASAL 21</b>", small), Spacer(1, 2)]
    bold = {"i8", "i11", "i12", "i14", "i16", "i17", "i19", "i20"}
    rows = [[label, rp(f["items"][k])] for k, label in ITEM_LABELS]
    t = Table(rows, colWidths=[140 * mm, 42 * mm])
    style = [("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]
    for i, (k, _) in enumerate(ITEM_LABELS):
        if k in bold:
            style += [("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"), ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F1F5F9"))]
    t.setStyle(TableStyle(style))
    diff = f["difference"]
    note = "Kurang bayar" if diff > 0 else "Lebih bayar" if diff < 0 else "Nihil"
    els += [t, Spacer(1, 6), Paragraph(f"Selisih PPh 21 terutang vs dipotong: <b>{rp(diff)}</b> ({note}).", small),
            Spacer(1, 10), Paragraph("Dokumen ini dihasilkan dari RUSA (RUMAT Salary Administration) "
                                     "sebagai bukti potong internal. "
                                     "Bukti potong resmi diterbitkan melalui aplikasi e-Bupot / Coretax DJP.", small)]
    doc.build(els)
    return buf.getvalue()
