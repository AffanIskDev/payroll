"""Export Data Payroll (Excel) — user 3 Nov 2026. Uji murni: tanpa server, tanpa database.

Rumus Excel di berkas dihitung ulang di sini (evaluator kecil) lalu dibandingkan dengan Take Home Pay slip RUSA —
itulah fungsi kolom "cek" di berkas acuan, yang sengaja tidak dimasukkan ke berkas hasil."""
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import integrations  # noqa: E402
from engine import compute_payslip  # noqa: E402
from export_data import ADVANCE, build_workbook  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"payroll_status": "active", "basic_salary": 4500000, "position_allowance": 500000,
       "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}
OKT = {"id": "p10", "period_name": "Oktober 2026", "start_date": "2026-10-01", "end_date": "2026-10-31"}
NOW = datetime(2026, 11, 3, 9, 40)


def _day(status):
    return integrations.normalize_attendance({
        "work_date": "2026-10-05", "status_ham": status, "minutes_late": 0, "minutes_early_leave": 0,
        "is_missing_check_in": False, "is_missing_check_out": False})


def _slip(nik, adj=None, emp=None, logs=(), **kw):
    s = compute_payslip({**EMP, **(emp or {})}, list(logs), CFG, adj or {})
    s.update({"employee_id": "id-" + nik, "status": "draft", "is_manually_adjusted": False,
              "employee": {"nik": nik, "name": "Nama " + nik, "department": "Perawat",
                           "bank_account_number": "7123456789"}, **kw})
    return s


def _open(slips, names=None):
    wb = load_workbook(io.BytesIO(build_workbook(OKT, slips, names or {}, NOW)))
    ws = wb.worksheets[0]
    head = {ws.cell(5, j).value: j for j in range(1, ws.max_column + 1) if ws.cell(5, j).value}
    return wb, ws, head


def _eval(ws, ref):
    """Nilai sel; rumus =SUM(A1:B1) / + / - / referensi sel dihitung ulang."""
    v = ws[ref].value
    if not (isinstance(v, str) and v.startswith("=")):
        return v or 0

    def rng(m):
        a, b = m.group(1), m.group(2)
        r = int(re.sub(r"\D", "", a))
        c1, c2 = column_index_from_string(re.sub(r"\d", "", a)), column_index_from_string(re.sub(r"\d", "", b))
        return str(sum(_eval(ws, ws.cell(r, c).coordinate) for c in range(c1, c2 + 1)))
    f = re.sub(r"SUM\(([A-Z]+\d+):([A-Z]+\d+)\)", rng, v[1:])
    f = re.sub(r"[A-Z]+\d+", lambda m: str(_eval(ws, m.group(0))), f)
    return eval(f)  # hanya angka dan + - dari rumus buatan sendiri


def _thp(ws, head, row):
    return _eval(ws, ws.cell(row, head["TAKE HOME PAY"]).coordinate)


def test_thp_formula_equals_the_slip_take_home_pay_for_every_kind_of_slip():
    slips = [
        _slip("1001"),
        _slip("1002", {"transport_homecare": 1250000}),                                   # transport dibayar di muka
        _slip("1003", {"transport_homecare": 800000, "other_deductions": 50000, "target_deduction": 500000,
                       "loan_installment": 100000}, logs=[_day("izin")]),
        _slip("1004", emp={"payroll_status": "unpaid_leave"}),
    ]
    _, ws, head = _open(slips)
    for i, s in enumerate(slips):
        assert _thp(ws, head, 6 + i) == s["take_home_pay"], s["employee"]["nik"]


def test_refund_is_added_back_in_the_thp_formula():
    ctx = {"tax_year": 2026, "has_initial_balance": True, "initial_months": 9, "initial_gross": 43053400.0,
           "initial_jht_jp": 0.0, "initial_pph21": 336501.0, "system_gross": 0, "system_jht_jp": 0, "system_pph21": 0,
           "system_months": 0, "kind": "keluar", "final_month": 10}
    s = compute_payslip({**EMP, "id": "e1", "exit_date": "2026-10-06", "join_date": "2024-03-01"}, [], CFG, {}, ctx, OKT)
    assert s["pph21_refund"] == 336501                          # lebih bayar -> pendapatan, bukan potongan negatif
    s.update({"employee_id": "id-1", "status": "draft", "is_manually_adjusted": False,
              "employee": {"nik": "1", "name": "Nama 1", "department": "Perawat"}})
    _, ws, head = _open([s])
    assert ws.cell(6, head["Pengembalian PPh 21 (lebih bayar)"]).value == 336501
    assert ws.cell(6, head["PPh 21 Dipotong"]).value == 0
    assert _thp(ws, head, 6) == s["take_home_pay"]


def test_layout_matches_the_reference_file_and_has_no_check_columns():
    _, ws, head = _open([_slip("1001"), _slip("1002")])
    titles = list(head)
    assert titles[:5] == ["No", "NIK", "Nama (sesuai Rekening)", "Departemen", "Status / Keterangan"]
    assert titles[-1] == "TAKE HOME PAY"                       # berakhir di THP: tanpa "THP menurut Slip" & "Selisih"
    assert not any("Selisih" in t or "menurut Slip" in t for t in titles)
    assert ws.title == "Payroll Okt 2026" and ws["A1"].value == "Data Payroll Oktober 2026 - RUSA (per karyawan)"
    assert ws.freeze_panes == "D6" and ws.cell(5, 1).value == "No"
    groups = [ws.cell(4, j).value for j in range(1, ws.max_column + 1) if ws.cell(4, j).value]
    assert groups == ["IDENTITAS", "PENDAPATAN", "POTONGAN PRESENSI & ABSENSI", "PAJAK PPh 21",
                      "IURAN BPJS (dipotong dari gaji)", "TOTAL"]
    assert ws.cell(8, 3).value == "TOTAL"                      # baris total sesudah data (2 karyawan: baris 6-7)
    assert ws.cell(8, head["TAKE HOME PAY"]).value == "=SUM(%s6:%s7)" % ((ws.cell(8, head["TAKE HOME PAY"]).column_letter,) * 2)


def test_without_transport_in_advance_the_extra_column_is_left_out():
    _, _, head = _open([_slip("1001")])
    assert ADVANCE not in head
    _, ws, head = _open([_slip("1001"), _slip("1002", {"transport_homecare": 800000})])
    assert ADVANCE in head and head[ADVANCE] == head["TAKE HOME PAY"] - 1   # tepat sebelum THP
    assert ws.cell(7, head[ADVANCE]).value == 800000 and ws.cell(6, head[ADVANCE]).value == 0
    # transport tetap pendapatan & bruto kena pajak, bukan potongan
    assert ws.cell(7, head["Transport Homecare"]).value == 800000
    assert ws.cell(7, head["Potongan Lain (Target/Cicilan/Lainnya)"]).value == 0


def test_name_follows_the_bank_account_and_row_is_highlighted_for_pasal17_unpaid_and_keluar():
    slips = [_slip("1001"), _slip("1002", emp={"payroll_status": "unpaid_leave"}),
             _slip("1003", pph21_method="pasal17", ter_rate=0)]
    _, ws, head = _open(slips, {"id-1001": "Nama Di Rekening"})
    assert ws.cell(6, 3).value == "Nama Di Rekening" and ws.cell(7, 3).value == "Nama 1002"   # tanpa nama rekening: nama HAM
    assert ws.cell(6, 5).value == "Aktif" and "Unpaid" in ws.cell(7, 5).value
    assert "Pajak Pasal 17" in ws.cell(8, 5).value and ws.cell(8, head["Tarif (%)"]).value is None
    assert ws.cell(6, 1).fill.fgColor.rgb in (None, "00000000") and ws.cell(7, 1).fill.fgColor.rgb.endswith("FFF2CC")
    assert ws.cell(8, 1).fill.fgColor.rgb.endswith("FFF2CC")


def test_no_account_number_or_other_private_data_in_the_file():
    wb, _, _ = _open([_slip("1001")])
    text = " ".join(str(c.value) for w in wb for r in w.iter_rows() for c in r if c.value is not None)
    assert "7123456789" not in text and "NPWP" not in text.replace("Tidak disertakan: nomor rekening, NPWP, alamat.", "")
    assert [w.title for w in wb] == ["Payroll Okt 2026", "Catatan"]
