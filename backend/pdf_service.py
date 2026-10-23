import io
import secrets
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from labels import PJUNIT_TARGET_NOTE, position_allowance_label
from periods import BULAN

STORAGE = Path(__file__).parent / "storage" / "payslips"
STORAGE.mkdir(parents=True, exist_ok=True)
# "Tanda tangan" slip = QR verifikasi per slip (user 14 Okt 2026, verify.py), bukan gambar tanda tangan. Ukuran sudah
# termasuk zona tenang QR (4 modul di tiap sisi): ±0,6 mm per modul, aman dipindai dari kertas maupun layar HP.
QR_SIZE = 24 * mm
ASSETS = Path(__file__).parent / "assets"
LOGO_H = 14 * mm  # same height as the e-recruitment offering letter header
# logo RUMAT lebar (rasio 4:1): pada tinggi yang sama ia tiga kali luas logo RPI, jadi dibuat lebih pendek supaya
# tidak terlalu dominan (permintaan user 10 Okt 2026)
RUMAT_LOGO_H = 11 * mm
LINE = 12  # one blank line (pt) at the slip's body text size
NAVY = colors.HexColor("#0F172A")
WIB = timezone(timedelta(hours=7))  # tanpa musim panas: offset tetap cukup


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


REFUND_LABEL = "Pengembalian Perusahaan"
REFUND_NOTE = "lebih bayar PPh 21"  # keterangan di bawah baris Pengembalian Perusahaan (user 21 Okt 2026)


def tk_rate_label(slip: dict) -> str:
    """Persen iuran BPJS Ketenagakerjaan (perusahaan + karyawan) terhadap upah terdaftar, seperti "(5%)" di Kesehatan.
    Upah terdaftar dibaca balik dari program yang iurannya bukan persen JP (JHT karyawan 2%, JKM 0,3%, JKK 0,24%);
    slip lama tanpa rincian BPJS tampil tanpa persen."""
    bp = slip.get("bpjs") or {}
    base = next((bp[k] / r for k, r in (("jht_employee", 0.02), ("jkm", 0.003), ("jkk", 0.0024)) if bp.get(k)), 0)
    if not base:
        return ""
    pct = round(slip["iuran_bpjs_tk_total"] / base * 100, 2)
    return f" ({f'{pct:.2f}'.rstrip('0').rstrip('.').replace('.', ',')}%)"


def _shown(rows):
    """Rows worth printing: a zero amount says nothing to the employee — except PPh 21 and the totals.
    Rows are (label, value, always[, detail]); returns (label, value, detail)."""
    return [(r[0], r[1], r[3] if len(r) > 3 else "") for r in rows if r[2] or round(r[1] or 0) != 0]


# short names of absence days, in PPT order. alfa/izin/cuti tanpa upah (also cost gaji pokok & tunjangan jabatan)
# are detailed under Potongan Absensi; the others only cut the attendance allowance and sit under Potongan Presensi
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
    """Poin Presensi: lateness (Rule 1-4) plus the days off that only cut the attendance allowance (sakit, cuti)."""
    d = slip.get("discipline") or {}
    late = [fmt.format(d[k]) for k, fmt in PRESENCE_NAMES if d.get(k)]
    by_type = d.get("presence_by_type") or {}
    days = [f"{by_type[t]} hari {name}" for t, name in ABSENCE_NAMES.items() if by_type.get(t)]
    return ", ".join(late + days) or f"{slip.get('late_penalty_points', 0)} poin"


def _logo(name: str, max_w: float, logo_h: float = LOGO_H) -> Image:
    path = ASSETS / name
    w, h = ImageReader(str(path)).getSize()
    height = logo_h if w * logo_h / h <= max_w else max_w * h / w
    return Image(str(path), width=w * height / h, height=height, mask="auto")


def _qr(url: str) -> Drawing:
    """The verification QR of a slip: vector, so it stays sharp when printed or zoomed on a phone."""
    widget = qr.QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    d = Drawing(QR_SIZE, QR_SIZE, transform=[QR_SIZE / (x1 - x0), 0, 0, QR_SIZE / (y1 - y0), 0, 0])
    d.hAlign = "CENTER"
    d.add(widget)
    return d


def _verify_note(url: str, style: ParagraphStyle) -> Paragraph:
    """Under the QR: what it is, and the address itself as a link — the slip is read on a phone, which cannot scan its
    own screen, and in a PDF viewer the link opens the same page."""
    shown = escape(url.split("://", 1)[-1])
    return Paragraph(f'Pindai QR untuk memverifikasi keaslian slip<br/><link href="{escape(url, {chr(34): "&quot;"})}" '
                     f'color="#1D4ED8">{shown}</link>', style)


def _tanggal(iso: str) -> str:
    """'15 Oktober 2026': tanggal WIB dari waktu ISO (UTC) yang disimpan."""
    d = datetime.fromisoformat(iso).astimezone(WIB)
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def _doc_line(slip: dict) -> str:
    """Di bawah judul: nomor dokumen & tanggal terbit yang juga ditampilkan halaman verifikasi (user 15 Okt 2026), supaya
    keduanya bisa dicocokkan. Draft belum punya keduanya — dan memang bukan slip resmi."""
    if slip.get("status") != "approved":
        return "<b>DRAFT</b> — belum disetujui; nomor dokumen diberikan saat disetujui"
    parts = [f"No. <b>{escape(slip['doc_number'])}</b>"] if slip.get("doc_number") else []  # approved sebelum 15 Okt: tanpa nomor
    if slip.get("approved_at"):
        parts.append(f"Diterbitkan {_tanggal(slip['approved_at'])}")
    return " · ".join(parts)


def _rekening(emp: dict) -> str:
    """'3324259820 (BSI)': account number, then the bank's short code."""
    bank = (emp.get("bank_code") or "").strip().upper() or emp.get("bank_name") or ""
    norek = emp.get("bank_account_number") or ""
    return (f"{norek} ({bank})" if bank else norek) if norek else (bank or "-")


def _jam_menit(h) -> str:
    """Overtime hours as '25 jam 58 menit': paid per minute like the drivers' Excel recap (user 11 Oct 2026)."""
    j, m = divmod(round(float(h or 0) * 60), 60)
    if j and m:
        return f"{j} jam {m} menit"
    return f"{j} jam" if j else f"{m} menit"


def _prorata_details(slip: dict) -> tuple:
    """(gapok, jabatan, kehadiran): keterangan gaji tidak penuh (user 15 Okt 2026, engine.prorata), '' bila penuh —
    'prorata 15/25 hari kerja, masuk 14 Sep' di Gaji Pokok, angka hari kerjanya saja di jabatan & kehadiran."""
    pr = slip.get("prorata") or {}
    basic = att = jabatan = ""
    if pr.get("basic_factor", 1) < 1:
        jabatan = f"prorata {pr['work_days']}/{pr['divisor']} hari kerja"
        when = {"masuk": f"masuk {_tanggal_pendek(pr['from'])}", "keluar": f"keluar {_tanggal_pendek(pr['to'])}",
                "masuk_keluar": f"{_tanggal_pendek(pr['from'])} s/d {_tanggal_pendek(pr['to'])}"}.get(pr["kind"])
        basic = f"{jabatan}, {when}" if when else jabatan
    if pr.get("attendance_factor", 1) < 1:
        att = f"prorata {pr['attendance_days']}/{pr['divisor']} hari kerja" + (
            " di luar cuti melahirkan" if pr.get("kind") == "cuti_melahirkan" else "")
    return basic, jabatan, att


def _tanggal_pendek(iso: str) -> str:
    """'14 Sep' — tahunnya sudah ada di Periode slip; dengan tahun keterangan Gaji Pokok turun ke baris ketiga."""
    d = date_cls.fromisoformat(iso[:10])
    return f"{d.day} {BULAN[d.month - 1][:3]}"


def payslip_lines(slip: dict) -> tuple:
    """PENDAPATAN and POTONGAN rows as printed (user requests 9 Oct): allowances in full under PENDAPATAN; every
    attendance-related cut under POTONGAN as just two lines — Potongan Presensi (lateness points plus sakit/cuti
    days, which only cut the attendance allowance) and Potongan Absensi (alfa/izin/cuti tanpa upah days: their
    attendance-allowance cut plus the gaji pokok and tunjangan jabatan cuts of the PPT). Both totals carry the
    cuts, so TOTAL PENDAPATAN - TOTAL POTONGAN = TOTAL DITERIMA. THR and Cicilan / Pinjaman (ROSY Tambahan Bulanan,
    12 Oct) print only when set; a PJUnit reads "Bonus Threshold" for the tunjangan jabatan (labels.py, by jabatan).
    A PJUnit's Potongan Tidak Mencapai Target is already off their Bonus Threshold (engine, 13 Oct): that row says so,
    even at Rp 0, with the note "Income Unit Minimal 20 jt" (user 14 Oct), and the potongan row shows only what the
    Bonus Threshold could not cover."""
    split = "presence_penalty_amount" in slip  # slips calculated before 9 Oct only have the net allowance
    # slips calculated before 12 Oct carry no label yet; their snapshot has no jabatan, so they read "Tunjangan
    # Jabatan" — as they were issued, before "Bonus Threshold" existed
    jabatan = slip.get("position_allowance_label") or position_allowance_label(slip.get("employee"))
    from_bonus = slip.get("target_from_bonus", 0)
    basic_pr, jabatan_pr, att_pr = _prorata_details(slip)
    jabatan_detail = ", ".join(x for x in (PJUNIT_TARGET_NOTE if from_bonus else "", jabatan_pr) if x)
    presensi = slip.get("presence_penalty_amount", 0)
    absensi = (slip.get("absence_penalty_amount", 0) + slip["absent_deduction_amount"]
               + slip.get("position_deduction_amount", 0))
    kehadiran = (("Tunjangan Kehadiran", slip["attendance_allowance_base"]) if split
                 else ("Tunj. Kehadiran (bersih)", slip["attendance_allowance"]))
    # Lebih bayar PPh 21 masa terakhir = pendapatan, bukan potongan negatif (user 21 Okt 2026). Slip yang dihitung
    # sebelum itu tak punya `pph21_refund`: PPh minusnya tetap di Potongan, seperti saat diterbitkan
    refund = slip.get("pph21_refund", 0)
    pph21 = slip["pph21_amount"] if "pph21_refund" not in slip else max(slip["pph21_amount"], 0)
    # Unpaid / cuti di luar tanggungan (user 23 Okt 2026): tiga komponen tetap dicetak dengan Rp 0, bukan dihilangkan
    unpaid = slip.get("payroll_status") == "unpaid_leave"
    earn = _shown([("Gaji Pokok", slip["basic_salary"], unpaid, basic_pr),
                   (jabatan, slip["position_allowance"], bool(from_bonus) or unpaid, jabatan_detail),
                   (*kehadiran, unpaid, att_pr),
                   (f"Lembur ({_jam_menit(slip['overtime_hours'])})", slip["overtime_pay"], False),
                   ("Transport Homecare", slip.get("transport_homecare", 0), False),
                   ("Insentif KPI", slip["kpi_incentive"], False), ("Bonus", slip["additional_bonus"], False),
                   ("THR", slip.get("thr", 0), False),
                   ("Tunj. BPJS Kesehatan", slip["tunjangan_bpjs_kes"], False),
                   ("Tunj. BPJS Ketenagakerjaan", slip["tunjangan_bpjs_tk"], False),
                   (REFUND_LABEL, refund, False, REFUND_NOTE),
                   ("TOTAL PENDAPATAN", slip["gross_earnings"] + presensi + absensi + refund, True)])
    ded = _shown([("Potongan Presensi", presensi, False, _presence_detail(slip)),
                  ("Potongan Absensi", absensi, False, _absence_detail(slip)),
                  ("Potongan Tidak Mencapai Target", slip.get("target_deduction", 0), False),
                  ("Iuran BPJS Kesehatan (5%)", slip["iuran_bpjs_kes_total"], False),
                  (f"Iuran BPJS Ketenagakerjaan{tk_rate_label(slip)}", slip["iuran_bpjs_tk_total"], False),
                  ((("PPh 21 Masa Terakhir (Pasal 17)"
                     if (slip.get("tax_reconciliation") or {}).get("kind") == "keluar"
                     else "PPh 21 Desember (Pasal 17)") if slip.get("pph21_method") == "pasal17"
                    else f"PPh 21 TER {slip['ter_category']} ({slip['ter_rate']}%)"), pph21, True),
                  ("Cicilan / Pinjaman", slip.get("loan_installment", 0), False),
                  ("Kasbon / Potongan Lain", slip["other_deductions"], False),
                  ("TOTAL POTONGAN", slip["total_deductions"] + presensi + absensi, True)])
    return earn, ded


def render_payslip(slip: dict, period: dict) -> bytes:
    buf = io.BytesIO()
    # margin 22 mm kiri-kanan: bidang tulis = lebar isi slip (166 mm), jadi isi di tengah halaman dan catatan
    # CONFIDENTIAL tidak melebar melewati kotak-kotak di atasnya
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=12 * mm)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=10)
    emp = slip["employee"]
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=ss["Title"].fontSize * 0.7,
                           leading=ss["Title"].leading * 0.7)
    # Kop like the e-recruitment offering letter: RPI (PT Rumah Perawatan Indonesia) left, RUMAT right
    kop = Table([[_logo("logo-rpi.png", 58 * mm), _logo("logo-rumat.png", 58 * mm, RUMAT_LOGO_H)]],
                colWidths=[83 * mm, 83 * mm])
    kop.hAlign = "LEFT"
    # MIDDLE: logo RUMAT yang lebih pendek berada di tengah tinggi logo RPI, bukan menempel di atas
    kop.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    # jarak kop → judul → identitas: +1 baris di bawah logo (9 Okt pagi sempat +3 baris, dinilai terlalu jauh).
    # Baris nomor dokumen (15 Okt) memakai sebagian jarak judul → identitas: blok identitas tidak bergeser
    doc_no = ParagraphStyle("no", parent=small, alignment=TA_CENTER, textColor=colors.HexColor("#475569"))
    els = [kop, Spacer(1, 20 + LINE), Paragraph("<b>SLIP GAJI KARYAWAN</b>", title), Paragraph(_doc_line(slip), doc_no),
           Spacer(1, 18 - doc_no.leading)]
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
    # teks disclaimer dari user 9 Okt 2026
    disclaimer = Table([[Paragraph("<b>Catatan:</b> Slip gaji ini dibuat berdasarkan data yang tersedia pada saat proses "
                                   "payroll dilakukan. Apabila di kemudian hari ditemukan adanya kesalahan perhitungan, "
                                   "perusahaan berhak melakukan koreksi dan penyesuaian sesuai ketentuan yang berlaku.",
                                   note)]],
                       colWidths=[166 * mm])  # selebar kotak total
    disclaimer.hAlign = "LEFT"
    disclaimer.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEE2E2")),
                                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#DC2626")),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    els += [total, Spacer(1, 6), disclaimer, Spacer(1, 12)]
    # Penandatangan = Document Signer payroll di ROSY (disimpan di periode saat sinkron); kosong bila belum ada.
    # "Tanda tangan"-nya QR verifikasi slip ini (user 14 Okt 2026, verify.py), bukan gambar tanda tangan; tanpa
    # alamat verifikasi (slip lama / alamat belum bisa ditentukan) ruangnya tetap kosong
    signer = period.get("signer") or {}
    verify_url = slip.get("verify_url") or ""
    caption = ParagraphStyle("q", parent=small, fontSize=6.5, leading=8, alignment=TA_CENTER,
                             textColor=colors.HexColor("#475569"))
    rows = [["", "Disetujui oleh,"], ["", _qr(verify_url) if verify_url else ""], ["", signer.get("nama") or ""],
            ["", signer.get("jabatan") or ""]]
    heights = [5 * mm, QR_SIZE + 2 * mm if verify_url else 14 * mm, 5 * mm, 7 * mm]  # jabatan 7 mm: jarak di bawah garis
    if verify_url:
        rows.append(["", _verify_note(verify_url, caption)])
        heights.append(None)
    sign = Table(rows, colWidths=[106 * mm, 60 * mm], rowHeights=heights)
    sign.hAlign = "LEFT"
    sign.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (1, -1), "CENTER"),
                              ("VALIGN", (1, 1), (1, 1), "MIDDLE"),
                              ("TOPPADDING", (1, 1), (1, 1), 0), ("BOTTOMPADDING", (1, 1), (1, 1), 0),
                              ("TOPPADDING", (1, 4), (1, 4), 0), ("BOTTOMPADDING", (1, 4), (1, 4), 0),
                              ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
                              ("LINEBELOW", (1, 2), (1, 2), 0.5, NAVY)]))
    # 7 pt: satu baris (154 mm) di dalam lebar isi 166 mm — pada 8 pt sisa "tanpa izin HRD." turun sendirian
    confidential = ParagraphStyle("c", parent=small, fontSize=7, leading=9)
    els += [sign, Spacer(1, 10), Paragraph("<b>CONFIDENTIAL</b> — Dokumen ini bersifat rahasia dan hanya untuk karyawan "
                                           "yang bersangkutan. Dilarang menyebarluaskan tanpa izin HRD.", confidential)]
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
