import io
import secrets
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

STORAGE = Path(__file__).parent / "storage" / "payslips"
STORAGE.mkdir(parents=True, exist_ok=True)
ASSETS = Path(__file__).parent / "assets"
LOGO_H = 14 * mm  # same height as the e-recruitment offering letter header
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


def _shown(rows):
    """Rows worth printing: a zero amount says nothing to the employee — except PPh 21 and the totals."""
    return [(k, v) for k, v, always in rows if always or round(v or 0) != 0]


def _logo(name: str, max_w: float) -> Image:
    path = ASSETS / name
    w, h = ImageReader(str(path)).getSize()
    height = LOGO_H if w * LOGO_H / h <= max_w else max_w * h / w
    return Image(str(path), width=w * height / h, height=height, mask="auto")


def _rekening(emp: dict) -> str:
    """'3324259820 (BSI)': account number, then the bank's short code."""
    bank = (emp.get("bank_code") or "").strip().upper() or emp.get("bank_name") or ""
    norek = emp.get("bank_account_number") or ""
    return (f"{norek} ({bank})" if bank else norek) if norek else (bank or "-")


def _jam(h) -> str:
    return f"{float(h or 0):g}".replace(".", ",")


def payslip_lines(slip: dict) -> tuple:
    """PENDAPATAN and POTONGAN rows as printed. The alfa/izin cuts of gaji pokok and tunjangan jabatan are
    shown under POTONGAN (user request 9 Oct), so both totals carry them and
    TOTAL PENDAPATAN - TOTAL POTONGAN = TOTAL DITERIMA."""
    alfa_izin = f"{slip.get('absent_days', 0)} hari alfa/izin"
    gapok_cut = slip["absent_deduction_amount"]
    jabatan_cut = slip.get("position_deduction_amount", 0)  # absent on slips approved before 9 Oct
    earn = _shown([("Gaji Pokok", slip["basic_salary"], False),
                   ("Tunjangan Jabatan", slip["position_allowance"], False),
                   ("Tunj. Kehadiran (bersih)", slip["attendance_allowance"], False),
                   (f"Lembur ({_jam(slip['overtime_hours'])} jam)", slip["overtime_pay"], False),
                   ("Transport Homecare", slip.get("transport_homecare", 0), False),
                   ("Insentif KPI", slip["kpi_incentive"], False), ("Bonus Tambahan", slip["additional_bonus"], False),
                   ("Tunj. BPJS Kesehatan", slip["tunjangan_bpjs_kes"], False),
                   ("Tunj. BPJS Ketenagakerjaan", slip["tunjangan_bpjs_tk"], False),
                   ("TOTAL PENDAPATAN", slip["gross_earnings"] + gapok_cut + jabatan_cut, True)])
    ded = _shown([(f"Potongan Gaji Pokok ({alfa_izin})", gapok_cut, False),
                  (f"Potongan Tunj. Jabatan ({alfa_izin})", jabatan_cut, False),
                  ("Iuran BPJS Kesehatan (5%)", slip["iuran_bpjs_kes_total"], False),
                  ("Iuran BPJS Ketenagakerjaan", slip["iuran_bpjs_tk_total"], False),
                  (("PPh 21 Desember (Pasal 17)" if slip.get("pph21_method") == "pasal17"
                    else f"PPh 21 TER {slip['ter_category']} ({slip['ter_rate']}%)"), slip["pph21_amount"], True),
                  ("Kasbon / Potongan Lain", slip["other_deductions"], False),
                  ("TOTAL POTONGAN", slip["total_deductions"] + gapok_cut + jabatan_cut, True)])
    return earn, ded


def render_payslip(slip: dict, period: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=10)
    emp = slip["employee"]
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=ss["Title"].fontSize * 0.7,
                           leading=ss["Title"].leading * 0.7)
    # Kop like the e-recruitment offering letter: RPI (PT Rumah Perawatan Indonesia) left, RUMAT right
    kop = Table([[_logo("logo-rpi.png", 58 * mm), _logo("logo-rumat.png", 58 * mm)]], colWidths=[83 * mm, 83 * mm])
    kop.hAlign = "LEFT"
    kop.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    els = [kop, Spacer(1, 20), Paragraph("<b>SLIP GAJI KARYAWAN</b>", title), Spacer(1, 18)]
    # 5 kolom = garis tabel di bawahnya: kiri sejajar PENDAPATAN (76 mm), jarak 14 mm, kanan sejajar POTONGAN
    info = [["NIK:", emp["nik"], "", "Periode:", period["period_name"]],
            ["Nama:", emp["name"], "", "Status PTKP:", f"{slip['ptkp_status']} (TER {slip['ter_category']})"],
            ["Departemen:", emp.get("department") or "-", "", "Rekening:", _rekening(emp)]]
    it = Table(info, colWidths=[25 * mm, 51 * mm, 14 * mm, 33 * mm, 43 * mm])
    it.hAlign = "LEFT"
    it.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"), ("FONTNAME", (1, 1), (1, 1), "Helvetica-Bold"),
                            ("ALIGN", (4, 0), (4, -1), "RIGHT")]))
    els += [it, Spacer(1, 8)]
    earn, ded = payslip_lines(slip)
    two = Table([[_col(earn, "PENDAPATAN"), _col(ded, "POTONGAN")]], colWidths=[90 * mm, 90 * mm])
    two.hAlign = "LEFT"
    # tanpa padding pembungkus: tepi tabel PENDAPATAN/POTONGAN tepat di 0, 90, 166 mm (garis acuan blok identitas & total)
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    els += [two, Spacer(1, 10)]
    green = colors.HexColor("#047857")
    words = ParagraphStyle("tb", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8, leading=10,
                           textColor=green, alignment=TA_RIGHT)
    # terbilang tepat DI BAWAH nominal, rata kanan dengan angkanya
    total = Table([["TOTAL DITERIMA", rp(slip["take_home_pay"])], ["", Paragraph(slip["terbilang"], words)]],
                  colWidths=[70 * mm, 96 * mm])  # = tepi kanan tabel POTONGAN (90 + 76 mm)
    total.hAlign = "LEFT"
    total.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                               ("TEXTCOLOR", (0, 0), (-1, -1), green), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 13 * 0.8),
                               ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                               ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]))
    note = ParagraphStyle("n", parent=small, textColor=colors.black)
    disclaimer = Table([[Paragraph("Apabila terdapat ketidaksesuaian pada rincian gaji ini, mohon segera menghubungi "
                                   "Divisi HRD untuk dilakukan pengecekan dan perbaikan.", note)]],
                       colWidths=[166 * mm])  # selebar kotak total
    disclaimer.hAlign = "LEFT"
    disclaimer.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEE2E2")),
                                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#DC2626")),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    els += [total, Spacer(1, 6), disclaimer, Spacer(1, 12)]
    # Penandatangan = Document Signer payroll di ROSY (disimpan di periode saat sinkron); kosong bila belum ada
    signer = period.get("signer") or {}
    sign = Table([["", "Disetujui oleh,"], ["", ""], ["", signer.get("nama") or ""],
                  ["", signer.get("jabatan") or ""]], colWidths=[106 * mm, 60 * mm],
                 rowHeights=[5 * mm, 14 * mm, 5 * mm, 5 * mm])
    sign.hAlign = "LEFT"
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


def save_encrypted(slip: dict, period: dict) -> str:
    data = encrypt_pdf(render_payslip(slip, period), birth_password(slip["employee"]["birth_date"]))
    path = STORAGE / f"{slip['id']}.pdf"
    path.write_bytes(data)
    return str(path)
