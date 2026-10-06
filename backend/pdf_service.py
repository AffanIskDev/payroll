import io
import secrets
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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
    t = Table(data, colWidths=[52 * mm, 34 * mm])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)), ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    return t


def render_payslip(slip: dict, period: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=10)
    emp = slip["employee"]
    els = [Paragraph("<b>SLIP GAJI KARYAWAN — HRIS ROSY / RUMATKU</b>", ss["Title"]),
           Paragraph(f"Periode: <b>{period['period_name']}</b> ({period['start_date']} s/d {period['end_date']}) "
                     f"— Tanggal Bayar: {period.get('payment_date') or '-'}", small), Spacer(1, 6)]
    info = [["NIK", emp["nik"], "Status PTKP Efektif", f"{slip['ptkp_status']} (TER {slip['ter_category']})"],
            ["Nama", emp["name"], "Bank", emp.get("bank_name") or "-"],
            ["Departemen", emp.get("department") or "-", "No. Rekening", emp.get("bank_account_number") or "-"]]
    it = Table(info, colWidths=[25 * mm, 55 * mm, 35 * mm, 55 * mm])
    it.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
    els += [it, Spacer(1, 8)]
    earn = [("Gaji Pokok", slip["basic_salary"]), ("Potongan Mangkir", -slip["absent_deduction_amount"]),
            ("Tunjangan Jabatan", slip["position_allowance"]),
            ("Tunj. Kehadiran (bersih)", slip["attendance_allowance"]),
            (f"Lembur ({slip['overtime_hours']} jam)", slip["overtime_pay"]), ("Insentif KPI", slip["kpi_incentive"]),
            ("Bonus Tambahan", slip["additional_bonus"]), ("Tunj. BPJS Kesehatan", slip["tunjangan_bpjs_kes"]),
            ("Tunj. BPJS Ketenagakerjaan", slip["tunjangan_bpjs_tk"]), ("TOTAL PENERIMAAN", slip["gross_earnings"])]
    ded = [("Iuran BPJS Kesehatan (5%)", slip["iuran_bpjs_kes_total"]),
           ("Iuran BPJS Ketenagakerjaan", slip["iuran_bpjs_tk_total"]),
           (f"PPh 21 TER {slip['ter_category']} ({slip['ter_rate']}%)", slip["pph21_amount"]),
           ("Kasbon / Potongan Lain", slip["other_deductions"]), ("TOTAL POTONGAN", slip["total_deductions"])]
    two = Table([[_col(earn, "PENERIMAAN"), _col(ded, "POTONGAN")]], colWidths=[90 * mm, 90 * mm])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    els += [two, Spacer(1, 10)]
    thp = Table([["TAKE HOME PAY", rp(slip["take_home_pay"])], [slip["terbilang"], ""]],
                colWidths=[110 * mm, 70 * mm])
    thp.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                             ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#047857")),
                             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 13),
                             ("FONTSIZE", (0, 1), (-1, 1), 8), ("SPAN", (0, 1), (1, 1)),
                             ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    d = slip["discipline"]
    els += [thp, Spacer(1, 8), Paragraph(
        f"Denda disiplin: Rule1 {d['rule1_points']} + Rule2 {d['rule2_points']} + Rule3 {d['rule3_points']} + "
        f"Rule4 {d['rule4_points']} = {d['total_points']} poin; hari potong kehadiran {slip['late_penalty_days']}/25; "
        f"potongan {rp(slip['late_penalty_amount'])}, kompensasi {rp(slip['late_penalty_compensation'])}.", small),
        Spacer(1, 10), Paragraph("<b>CONFIDENTIAL</b> — Dokumen ini bersifat rahasia dan hanya untuk karyawan "
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


def save_encrypted(slip: dict, period: dict) -> str:
    data = encrypt_pdf(render_payslip(slip, period), birth_password(slip["employee"]["birth_date"]))
    path = STORAGE / f"{slip['id']}.pdf"
    path.write_bytes(data)
    return str(path)
