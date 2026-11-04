"""Export Data Payroll (Excel) per periode gaji — user 3 Nov 2026.

Satu sheet "Payroll <Bln> <Tahun>" per karyawan: identitas, pendapatan, potongan presensi & absensi, PPh 21, iuran BPJS,
sampai TAKE HOME PAY (tanpa kolom cek), ditambah sheet "Catatan" berisi cara membaca. Bentuknya mengikuti berkas acuan
Data-Payroll-Oktober-2026-RUSA-v2.xlsx; kolom jumlah/turunan ditulis sebagai RUMUS Excel supaya bisa ditelusuri.
Tanpa nomor rekening, NPWP, dan alamat (hanya nama sesuai rekening)."""
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from core import db, require_manager
from periods import BULAN, RUN_GAJI, run_type_of
from pipeline import get_period

# Data gaji seluruh karyawan: Manager HRD saja, sama dengan Pajak & export transfer BSI (routes_tax)
router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_manager)])

N0 = '#,##0;[Red]-#,##0;"-"'
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ADVANCE = "Transport Homecare Dibayar di Muka (tidak ikut THP)"
GRP_COLOR = {"IDENTITAS": "1F4E78", "PENDAPATAN": "2E7D32", "POTONGAN PRESENSI & ABSENSI": "C77700",
             "PAJAK PPh 21": "6A1B9A", "IURAN BPJS (dipotong dari gaji)": "00838F", "TOTAL": "B71C1C"}
NO_TOTAL = ("Dasar Upah BPJS Kes", "Dasar Upah JP")


def _g(s: dict, k: str):
    return s.get(k) or 0


def _bpjs(k: str):
    return lambda s, i, n: ((s.get("bpjs") or {}).get(k) or 0)


def _status(s: dict) -> str:
    p = s.get("prorata") or {}
    t = []
    if s.get("payroll_status") == "unpaid_leave":
        t.append("Unpaid")
    if p.get("kind") == "keluar":
        t.append("Keluar %s s/d %s (prorata)" % (p.get("from"), p.get("to")))
    elif p.get("kind"):
        t.append("Prorata " + str(p.get("kind")))
    if s.get("pph21_method") == "pasal17":
        t.append("Pajak Pasal 17")
    if s.get("is_manually_adjusted"):
        t.append("Disesuaikan manual")
    return "; ".join(t) or "Aktif"


def _highlight(s: dict) -> bool:
    return (s.get("pph21_method") == "pasal17" or s.get("payroll_status") == "unpaid_leave"
            or (s.get("prorata") or {}).get("kind") == "keluar")


def _columns(with_advance: bool) -> list:
    """(judul, grup, lebar, format, nilai). Nilai = fungsi (slip, no, nama_rekening) atau rumus berisi token [Judul Kolom]."""
    c = []
    add = lambda title, group, width, fmt, val: c.append((title, group, width, fmt, val))
    # ---- identitas
    add("No", "IDENTITAS", 5, "0", lambda s, i, n: i)
    add("NIK", "IDENTITAS", 10, "@", lambda s, i, n: s["employee"]["nik"])
    add("Nama (sesuai Rekening)", "IDENTITAS", 38, "@", lambda s, i, n: n)
    add("Departemen", "IDENTITAS", 18, "@", lambda s, i, n: s["employee"].get("department") or "")
    add("Status / Keterangan", "IDENTITAS", 34, "@", lambda s, i, n: _status(s))
    # ---- pendapatan
    add("Gaji Pokok", "PENDAPATAN", 14, N0, lambda s, i, n: _g(s, "basic_salary"))
    add("Tunj. Jabatan", "PENDAPATAN", 14, N0, lambda s, i, n: _g(s, "position_allowance"))
    add("Tunj. Kehadiran (sebelum potongan)", "PENDAPATAN", 16, N0, lambda s, i, n: _g(s, "attendance_allowance_base"))
    add("Lembur", "PENDAPATAN", 12, N0, lambda s, i, n: _g(s, "overtime_pay"))
    add("Transport Homecare", "PENDAPATAN", 14, N0, lambda s, i, n: _g(s, "transport_homecare"))
    add("KPI / Insentif", "PENDAPATAN", 12, N0, lambda s, i, n: _g(s, "kpi_incentive"))
    add("Bonus Tambahan", "PENDAPATAN", 13, N0, lambda s, i, n: _g(s, "additional_bonus"))
    add("THR", "PENDAPATAN", 11, N0, lambda s, i, n: _g(s, "thr"))
    add("Tunj. BPJS Kes (porsi Perusahaan)", "PENDAPATAN", 15, N0, lambda s, i, n: _g(s, "tunjangan_bpjs_kes"))
    add("Tunj. BPJS TK (porsi Perusahaan)", "PENDAPATAN", 15, N0, lambda s, i, n: _g(s, "tunjangan_bpjs_tk"))
    add("Total Pendapatan Kotor", "PENDAPATAN", 16, N0, "=SUM([Gaji Pokok]:[Tunj. BPJS TK (porsi Perusahaan)])")
    # ---- potongan presensi & absensi
    g2 = "POTONGAN PRESENSI & ABSENSI"
    add("Pot. Presensi (Tunj. Kehadiran)", g2, 15, N0, lambda s, i, n: _g(s, "presence_penalty_amount"))
    add("Pot. Absensi - Tunj. Kehadiran", g2, 15, N0, lambda s, i, n: _g(s, "absence_penalty_amount"))
    add("Pot. Absensi - Gaji Pokok", g2, 15, N0, lambda s, i, n: _g(s, "absent_deduction_amount"))
    add("Pot. Absensi - Tunj. Jabatan", g2, 15, N0, lambda s, i, n: _g(s, "position_deduction_amount"))
    add("Total Pot. Presensi & Absensi", g2, 16, N0, "=SUM([Pot. Presensi (Tunj. Kehadiran)]:[Pot. Absensi - Tunj. Jabatan])")
    add("Poin Presensi", g2, 9, "0", lambda s, i, n: (s.get("discipline") or {}).get("presence_points", 0))
    add("Poin Absensi", g2, 9, "0", lambda s, i, n: (s.get("discipline") or {}).get("absence_points", 0))
    add("Pendapatan Setelah Potongan (Gaji Kotor Slip)", g2, 17, N0, "=[Total Pendapatan Kotor]-[Total Pot. Presensi & Absensi]")
    # ---- pajak
    g3 = "PAJAK PPh 21"
    add("Bruto Kena Pajak", g3, 16, N0, lambda s, i, n: _g(s, "taxable_gross"))
    add("PTKP", g3, 8, "@", lambda s, i, n: s.get("ptkp_status") or "")
    add("Metode / Kategori", g3, 12, "@",
        lambda s, i, n: "Pasal 17" if s.get("pph21_method") == "pasal17" else "TER " + (s.get("ter_category") or ""))
    add("Tarif (%)", g3, 9, "0.00%",
        lambda s, i, n: None if s.get("pph21_method") == "pasal17" else (s.get("ter_rate") or 0) / 100)
    add("PPh 21 Dipotong", g3, 14, N0, lambda s, i, n: max(_g(s, "pph21_amount"), 0))
    add("Pengembalian PPh 21 (lebih bayar)", g3, 15, N0, lambda s, i, n: _g(s, "pph21_refund"))
    # ---- iuran BPJS
    g4 = "IURAN BPJS (dipotong dari gaji)"
    add("Dasar Upah BPJS Kes", g4, 14, N0, _bpjs("kes_base"))
    add("Kes - Perusahaan", g4, 12, N0, _bpjs("kes_company"))
    add("Kes - Karyawan", g4, 12, N0, _bpjs("kes_employee"))
    add("Dasar Upah JP", g4, 14, N0, _bpjs("jp_base"))
    add("JHT - Perusahaan", g4, 12, N0, _bpjs("jht_company"))
    add("JHT - Karyawan", g4, 12, N0, _bpjs("jht_employee"))
    add("JP - Perusahaan", g4, 12, N0, _bpjs("jp_company"))
    add("JP - Karyawan", g4, 12, N0, _bpjs("jp_employee"))
    add("JKK", g4, 10, N0, _bpjs("jkk"))
    add("JKM", g4, 10, N0, _bpjs("jkm"))
    add("Total Iuran BPJS Kes", g4, 14, N0, "=[Kes - Perusahaan]+[Kes - Karyawan]")
    add("Total Iuran BPJS TK", g4, 14, N0, "=SUM([JHT - Perusahaan]:[JP - Karyawan])+[JKK]+[JKM]")
    # ---- total
    g5 = "TOTAL"
    add("Potongan Lain (Target/Cicilan/Lainnya)", g5, 15, N0,
        lambda s, i, n: _g(s, "other_deductions") + _g(s, "target_deduction") + _g(s, "loan_installment"))
    add("Total Potongan (Iuran + PPh 21 + Lain)", g5, 16, N0,
        "=[Total Iuran BPJS Kes]+[Total Iuran BPJS TK]+[PPh 21 Dipotong]+[Potongan Lain (Target/Cicilan/Lainnya)]")
    thp = "=[Pendapatan Setelah Potongan (Gaji Kotor Slip)]-[Total Potongan (Iuran + PPh 21 + Lain)]+[Pengembalian PPh 21 (lebih bayar)]"
    if with_advance:
        # Transport yang sudah dibayar di muka: tetap pendapatan & dasar pajak, bukan potongan, hanya dikecualikan dari THP
        add(ADVANCE, g5, 18, N0, lambda s, i, n: _g(s, "book_fee_homecare"))
        thp += "-[%s]" % ADVANCE
    add("TAKE HOME PAY", g5, 16, N0, thp)
    return c


def _notes(period: dict, slips: list, with_advance: bool) -> list:
    wd = next((s.get("work_days") for s in slips if s.get("work_days")), None) or 25
    notes = [
        "Cara membaca / rumus (sama dengan slip RUSA)",
        "",
        "Total Pendapatan Kotor = Gaji Pokok + Tunj. Jabatan + Tunj. Kehadiran (sebelum potongan) + Lembur + Transport Homecare + KPI + Bonus + THR + Tunj. BPJS Kes & TK (porsi Perusahaan).",
        "Tunj. BPJS Kes/TK porsi Perusahaan ditambahkan sebagai pendapatan, lalu seluruh iuran (Perusahaan + Karyawan) dipotong kembali di bagian IURAN BPJS.",
        "Pot. Presensi = (poin presensi / %d) x Tunj. Kehadiran. Pot. Absensi (alfa/izin) = (hari / %d) x (Gaji Pokok + Tunj. Jabatan + Tunj. Kehadiran), dipecah per komponen." % (wd, wd),
        "Pendapatan Setelah Potongan = Total Pendapatan Kotor - Total Pot. Presensi & Absensi (= 'Gaji Kotor' di slip).",
        "Bruto Kena Pajak = dasar PPh 21: pendapatan + BPJS Kes perusahaan 4% + JKK + JKM (+ penambah dasar pajak bila Dasar PPh 21 'kotor'); JHT/JP tidak masuk.",
        "PPh 21: metode TER (kategori A/B/C x tarif). Karyawan keluar / Pasal 17 memakai tarif Pasal 17; bila lebih bayar, selisihnya muncul di 'Pengembalian PPh 21' dan DITAMBAHKAN ke THP.",
        "Total Iuran BPJS Kes = Kes Perusahaan + Kes Karyawan. Total Iuran BPJS TK = JHT + JP (Perusahaan + Karyawan) + JKK + JKM.",
        "Total Potongan = Total Iuran BPJS Kes + Total Iuran BPJS TK + PPh 21 Dipotong + Potongan Lain.",
    ]
    if with_advance:
        notes += [
            "Transport Homecare sudah dibayar di muka: tetap masuk Pendapatan & dasar pajak, TIDAK dihitung sebagai potongan, hanya dikecualikan dari THP (kolom '%s')." % ADVANCE,
            "TAKE HOME PAY = Pendapatan Setelah Potongan - Total Potongan + Pengembalian PPh 21 - Transport Homecare Dibayar di Muka.",
        ]
    else:
        notes.append("TAKE HOME PAY = Pendapatan Setelah Potongan - Total Potongan + Pengembalian PPh 21.")
    notes += [
        "Baris dengan identitas berwarna kuning = karyawan Pasal 17 / keluar (prorata) / unpaid.",
        "Dasar upah BPJS (Kesehatan & Ketenagakerjaan) mengikuti pengaturan Konfigurasi RUSA dan data BPJS yang berlaku saat slip dihitung; yang tidak ikut = 0.",
        "Tidak disertakan: nomor rekening, NPWP, alamat.",
    ]
    return notes


def build_workbook(period: dict, slips: list, names: dict, now: datetime) -> bytes:
    """slips: slip RUSA satu periode (urut NIK); names: employee_id -> nama di rekening."""
    with_advance = any(_g(s, "book_fee_homecare") for s in slips)
    cols = _columns(with_advance)
    letter = {c[0]: L(j) for j, c in enumerate(cols, 1)}
    start = datetime.strptime(period["start_date"][:10], "%Y-%m-%d")
    bln, thn = BULAN[start.month - 1], start.year

    wb = Workbook()
    ws = wb.active
    ws.title = "Payroll %s %d" % (bln[:3], thn)
    thin = Side(style="thin", color="BFBFBF")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    n_draft = sum(1 for s in slips if s.get("status") != "approved")
    ws["A1"] = "Data Payroll %s %d - RUSA (per karyawan)" % (bln, thn)
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = ("Sumber: %d slip RUSA (%d draft, %d terkunci), diambil %d %s %d %s WIB. Angka dapat berubah sampai periode dikunci."
                % (len(slips), n_draft, len(slips) - n_draft, now.day, BULAN[now.month - 1][:3], now.year, now.strftime("%H.%M")))
    ws["A2"].font = Font(italic=True, color="595959")

    HG, HT, R0 = 4, 5, 6  # baris grup, baris judul, baris data pertama
    for gname in dict.fromkeys(c[1] for c in cols):
        idx = [j for j, c in enumerate(cols, 1) if c[1] == gname]
        ws.merge_cells(start_row=HG, start_column=idx[0], end_row=HG, end_column=idx[-1])
        cell = ws.cell(HG, idx[0], gname)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
        for j in idx:
            ws.cell(HG, j).fill = PatternFill("solid", fgColor=GRP_COLOR[gname])
            ws.cell(HG, j).border = bd
    for j, c in enumerate(cols, 1):
        h = ws.cell(HT, j, c[0])
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor=GRP_COLOR[c[1]])
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = bd
        ws.column_dimensions[L(j)].width = c[2]
    ws.row_dimensions[HT].height = 48

    for i, s in enumerate(slips, 1):
        r = R0 + i - 1
        for j, c in enumerate(cols, 1):
            v = c[4]
            if isinstance(v, str):
                v = re.sub(r"\[([^\]]+)\]", lambda m: "%s%d" % (letter[m.group(1)], r), v)
            else:
                v = v(s, i, names.get(s["employee_id"]) or s["employee"]["name"])
            cell = ws.cell(r, j, v)
            cell.number_format = c[3]
            cell.border = bd
            if c[0] == "TAKE HOME PAY":
                cell.font = Font(bold=True)
        if _highlight(s):
            for j in range(1, 6):
                ws.cell(r, j).fill = PatternFill("solid", fgColor="FFF2CC")
    last = R0 + len(slips) - 1
    total = last + 1
    ws.cell(total, 3, "TOTAL").font = Font(bold=True)
    for j, c in enumerate(cols, 1):
        if c[3] == N0 and c[0] not in NO_TOTAL:
            x = ws.cell(total, j, "=SUM(%s%d:%s%d)" % (L(j), R0, L(j), last))
            x.font = Font(bold=True)
            x.number_format = N0
            x.fill = PatternFill("solid", fgColor="DDEBF7")
            x.border = bd
    ws.freeze_panes = ws.cell(R0, 4)
    ws.auto_filter.ref = "A%d:%s%d" % (HT, L(len(cols)), last)

    cs = wb.create_sheet("Catatan")
    for i, t in enumerate(_notes(period, slips, with_advance), 1):
        cs.cell(i, 1, t).alignment = Alignment(wrap_text=True, vertical="top")
    cs["A1"].font = Font(bold=True, size=13)
    cs.column_dimensions["A"].width = 150

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.post("/periods/{pid}/export-data")
async def export_data(pid: str):
    period = await get_period(pid)
    if run_type_of(period) != RUN_GAJI:
        raise HTTPException(400, "Export Data Payroll hanya untuk periode gaji bulanan")
    slips = await db.payslips.find({"payroll_period_id": pid}, {"_id": 0}).sort("employee.nik", 1).to_list(5000)
    if not slips:
        raise HTTPException(400, "Belum ada slip pada periode ini")
    emps = {e["id"]: e.get("bank_account_name") or "" async for e in db.employees.find(
        {"id": {"$in": [s["employee_id"] for s in slips]}}, {"_id": 0, "id": 1, "bank_account_name": 1})}
    data = build_workbook(period, slips, {k: v.strip() for k, v in emps.items() if v and v.strip()},
                          datetime.now(ZoneInfo("Asia/Jakarta")))
    fname = "Data-Payroll-%s-RUSA.xlsx" % period["period_name"].replace(" ", "-")
    return Response(data, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{fname}"', "X-Exported-Count": str(len(slips))})
