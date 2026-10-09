import io
import secrets
from pathlib import Path
from xml.sax.saxutils import escape

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
LINE = 12  # one blank line (pt) at the slip's body text size
NAVY = colors.HexColor("#0F172A")


def rp(v) -> str:
    return "Rp " + f"{int(round(v or 0)):,}".replace(",", ".")


def birth_password(birth_date: str) -> str:
    y, m, d = birth_date.split("-")
    return f"{d}{m}{y[2:]}"


_DETAIL = ParagraphStyle("d", fontName="Helvetica", fontSize=8, leading=9.5)


def _label(k: str, detail: str):
    """Row label; a detail (e.g. '2 hari alfa, 1 hari izin') goes on a small grey second line."""
    if not detail:
        return k
    return Paragraph(f"{escape(k)}<br/><font size=6.5 color='#64748B'>{escape(detail)}</font>", _DETAIL)


def _col(rows, title):
    data = [[title, ""]] + [[_label(k, d), rp(v)] for k, v, d in rows]
    t = Table(data, colWidths=[46 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)), ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("VALIGN", (0, 1), (-1, -1), "TOP"),
    ]))
    return t


def _shown(rows):
    """Rows worth printing: a zero amount says nothing to the employee — except PPh 21 and the totals.
    Rows are (label, value, always[, detail]); returns (label, value, detail)."""
    return [(r[0], r[1], r[3] if len(r) > 3 else "") for r in rows if r[2] or round(r[1] or 0) != 0]


# short names for the Potongan Absensi detail, in PPT order (alfa/izin also cost gaji pokok & tunjangan jabatan)
ABSENCE_NAMES = {"alpha": "alfa", "permission_leave": "izin", "approved_unpaid_leave": "cuti tanpa upah",
                 "annual_leave": "cuti tahunan", "sick_with_certificate": "sakit", "statutory_leave": "cuti khusus",
                 "maternity_leave": "cuti melahirkan", "religious_leave": "cuti ibadah"}


def _absence_detail(slip: dict) -> str:
    by_type = (slip.get("discipline") or {}).get("absence_by_type") or {}
    if not by_type:  # slips calculated before the per-type breakdown existed
        n = slip.get("absence_points", slip.get("absent_days", 0))
        return f"{n} hari" if n else ""
    return ", ".join(f"{by_type[t]} hari {name}" for t, name in ABSENCE_NAMES.items() if by_type.get(t))


# Poin Presensi Rule 1-4 (engine.calc_discipline); plain ASCII/WinAnsi text — the base PDF font has no "≥"
PRESENCE_NAMES = (("rule1_points", "{}x lupa absen"), ("rule2_points", "{}x telat/pulang cepat min. 60 mnt"),
                  ("rule3_points", "{} poin telat 15–59 mnt"), ("rule4_points", "{} poin akumulasi telat <15 mnt"))


def _presence_detail(slip: dict) -> str:
    d = slip.get("discipline") or {}
    return (", ".join(fmt.format(d[k]) for k, fmt in PRESENCE_NAMES if d.get(k))
            or f"{slip.get('late_penalty_points', 0)} poin")


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
    """PENDAPATAN and POTONGAN rows as printed (user requests 9 Oct): allowances in full under PENDAPATAN; every
    attendance-related cut under POTONGAN as just two lines — Potongan Presensi (lateness points) and Potongan
    Absensi (absence days: the attendance-allowance cut plus, for alfa/izin, the gaji pokok and tunjangan jabatan
    cuts of the PPT). Both totals carry the cuts, so TOTAL PENDAPATAN - TOTAL POTONGAN = TOTAL DITERIMA."""
    split = "presence_penalty_amount" in slip  # slips calculated before 9 Oct only have the net allowance
    presensi = slip.get("presence_penalty_amount", 0)
    absensi = (slip.get("absence_penalty_amount", 0) + slip["absent_deduction_amount"]
               + slip.get("position_deduction_amount", 0))
    kehadiran = (("Tunjangan Kehadiran", slip["attendance_allowance_base"]) if split
                 else ("Tunj. Kehadiran (bersih)", slip["attendance_allowance"]))
    earn = _shown([("Gaji Pokok", slip["basic_salary"], False),
                   ("Tunjangan Jabatan", slip["position_allowance"], False),
                   (*kehadiran, False),
                   (f"Lembur ({_jam(slip['overtime_hours'])} jam)", slip["overtime_pay"], False),
                   ("Transport Homecare", slip.get("transport_homecare", 0), False),
                   ("Insentif KPI", slip["kpi_incentive"], False), ("Bonus Tambahan", slip["additional_bonus"], False),
                   ("Tunj. BPJS Kesehatan", slip["tunjangan_bpjs_kes"], False),
                   ("Tunj. BPJS Ketenagakerjaan", slip["tunjangan_bpjs_tk"], False),
                   ("TOTAL PENDAPATAN", slip["gross_earnings"] + presensi + absensi, True)])
    ded = _shown([("Potongan Presensi", presensi, False, _presence_detail(slip)),
                  ("Potongan Absensi", absensi, False, _absence_detail(slip)),
                  ("Iuran BPJS Kesehatan (5%)", slip["iuran_bpjs_kes_total"], False),
                  ("Iuran BPJS Ketenagakerjaan", slip["iuran_bpjs_tk_total"], False),
                  (("PPh 21 Desember (Pasal 17)" if slip.get("pph21_method") == "pasal17"
                    else f"PPh 21 TER {slip['ter_category']} ({slip['ter_rate']}%)"), slip["pph21_amount"], True),
                  ("Kasbon / Potongan Lain", slip["other_deductions"], False),
                  ("TOTAL POTONGAN", slip["total_deductions"] + presensi + absensi, True)])
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
    # jarak lega (A4 masih luas): +3 baris di bawah logo dan di bawah judul (permintaan 9 Okt)
    els = [kop, Spacer(1, 20 + 3 * LINE), Paragraph("<b>SLIP GAJI KARYAWAN</b>", title), Spacer(1, 18 + 3 * LINE)]
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
