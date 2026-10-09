import io
import secrets
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

STORAGE = Path(__file__).parent / "storage" / "payslips"
STORAGE.mkdir(parents=True, exist_ok=True)
NAVY = colors.HexColor("#0F172A")


def rp(v) -> str:
    return "Rp " + f"{int(round(v or 0)):,}".replace(",", ".")


def birth_password(birth_date: str) -> str:
    y, m, d = birth_date.split("-")
    return f"{d}{m}{y[2:]}"


def _col(rows, title):
    data = [[title, ""]] + [[k, rp(v)] for k, v in rows]
    t = Table(data, colWidths=[46 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)), ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    return t


def render_payslip(slip: dict, period: dict, cfg: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=10)
    emp = slip["employee"]
    head = ParagraphStyle("co", parent=ss["Normal"], fontSize=9, leading=11, textColor=NAVY)
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=ss["Title"].fontSize * 0.7,
                           leading=ss["Title"].leading * 0.7)
    els = [Paragraph(f"<b>{cfg.get('COMPANY_NAME', '')}</b><br/>{cfg.get('COMPANY_ADDRESS', '')}", head),
           Spacer(1, 4), Paragraph("<b>SLIP GAJI KARYAWAN</b>", title), Spacer(1, 6)]
    rekening = " ".join(v for v in (emp.get("bank_name"), emp.get("bank_account_number")) if v) or "-"
    # 5 kolom = garis tabel di bawahnya: kiri sejajar PENERIMAAN (76 mm), jarak 14 mm, kanan sejajar POTONGAN
    info = [["NIK", emp["nik"], "", "Periode", period["period_name"]],
            ["Nama", emp["name"], "", "Status PTKP Efektif", f"{slip['ptkp_status']} (TER {slip['ter_category']})"],
            ["Departemen", emp.get("department") or "-", "", "Rekening", rekening]]
    it = Table(info, colWidths=[25 * mm, 51 * mm, 14 * mm, 33 * mm, 43 * mm])
    it.hAlign = "LEFT"
    it.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"), ("FONTNAME", (1, 1), (1, 1), "Helvetica-Bold"),
                            ("ALIGN", (4, 0), (4, -1), "RIGHT")]))
    els += [it, Spacer(1, 8)]
    earn = [("Gaji Pokok", slip["basic_salary"]), ("Potongan Mangkir", -slip["absent_deduction_amount"]),
            ("Tunjangan Jabatan", slip["position_allowance"]),
            ("Tunj. Kehadiran (bersih)", slip["attendance_allowance"]),
            (f"Lembur ({slip['overtime_hours']} jam)", slip["overtime_pay"]), ("Insentif KPI", slip["kpi_incentive"]),
            ("Bonus Tambahan", slip["additional_bonus"]), ("Tunj. BPJS Kesehatan", slip["tunjangan_bpjs_kes"]),
            ("Tunj. BPJS Ketenagakerjaan", slip["tunjangan_bpjs_tk"]), ("TOTAL PENERIMAAN", slip["gross_earnings"])]
    ded = [("Iuran BPJS Kesehatan (5%)", slip["iuran_bpjs_kes_total"]),
           ("Iuran BPJS Ketenagakerjaan", slip["iuran_bpjs_tk_total"]),
           (("PPh 21 Desember (Pasal 17)" if slip.get("pph21_method") == "pasal17"
             else f"PPh 21 TER {slip['ter_category']} ({slip['ter_rate']}%)"), slip["pph21_amount"]),
           ("Kasbon / Potongan Lain", slip["other_deductions"]), ("TOTAL POTONGAN", slip["total_deductions"])]
    two = Table([[_col(earn, "PENERIMAAN"), _col(ded, "POTONGAN")]], colWidths=[90 * mm, 90 * mm])
    two.hAlign = "LEFT"
    # tanpa padding pembungkus: tepi tabel PENERIMAAN/POTONGAN tepat di 0, 90, 166 mm (garis acuan blok identitas & THP)
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    els += [two, Spacer(1, 10)]
    green = colors.HexColor("#047857")
    words = ParagraphStyle("tb", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, leading=10,
                           textColor=green, alignment=TA_RIGHT)
    # terbilang tepat DI BAWAH nominal, rata kanan dengan angkanya
    thp = Table([["TAKE HOME PAY", rp(slip["take_home_pay"])], ["", Paragraph(slip["terbilang"], words)]],
                colWidths=[70 * mm, 96 * mm])  # = tepi kanan tabel POTONGAN (90 + 76 mm)
    thp.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                             ("TEXTCOLOR", (0, 0), (-1, -1), green), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 13 * 0.8),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                             ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]))
    thp.hAlign = "LEFT"
    thp.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                             ("TEXTCOLOR", (0, 0), (-1, -1), green), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
                             ("FONTSIZE", (0, 0), (0, 0), 13 * 0.8), ("FONTSIZE", (2, 0), (2, 0), 13 * 0.8),
                             ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    els += [thp, Spacer(1, 18)]
    sign = Table([["", "Disetujui oleh,"], ["", ""], ["", cfg.get("PAYSLIP_SIGNATORY_NAME", "")],
                  ["", cfg.get("PAYSLIP_SIGNATORY_TITLE", "")]], colWidths=[120 * mm, 60 * mm],
                 rowHeights=[5 * mm, 14 * mm, 5 * mm, 5 * mm])
    sign.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (1, -1), "CENTER"),
                              ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
                              ("LINEBELOW", (1, 2), (1, 2), 0.5, NAVY)]))
    els += [sign, Spacer(1, 10), Paragraph("<b>CONFIDENTIAL</b> — Dokumen ini bersifat rahasia dan hanya untuk karyawan "
                                           "yang bersangkutan. Dilarang menyebarluaskan tanpa izin HRD.", small)]
    doc.build(els)
    return buf.getvalue()


def encrypt_pdf(pdf: bytes, password: str) -> bytes:
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=secrets.token_hex(16), algorithm="AES-256")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def save_encrypted(slip: dict, period: dict, cfg: dict) -> str:
    data = encrypt_pdf(render_payslip(slip, period, cfg), birth_password(slip["employee"]["birth_date"]))
    path = STORAGE / f"{slip['id']}.pdf"
    path.write_bytes(data)
    return str(path)
