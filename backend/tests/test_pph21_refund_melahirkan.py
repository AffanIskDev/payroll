"""Tiga perubahan user 21 Okt 2026:
1. Lebih bayar PPh 21 masa terakhir (Desember / bulan keluar) = Pendapatan "Pengembalian Perusahaan", bukan potongan
   negatif; kurang bayar tetap potongan PPh 21. Total Diterima tidak berubah, bruto & dasar pajak tidak ikut membesar.
2. Status karyawan aktif / keluar (pipeline.employment_info) untuk HRD.
3. Cuti melahirkan sepanjang periode: Tunjangan Kehadiran Rp 0 sejak awal (prorata tetap prorata).
Uji engine & PDF tanpa server dan tanpa database."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import integrations  # noqa: E402
from engine import compute_payslip  # noqa: E402
from pdf_service import payslip_lines  # noqa: E402
from pipeline import employment_info  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"id": "e1", "nik": "2024065", "name": "Uji Keluar", "payroll_status": "active", "basic_salary": 3000000,
       "position_allowance": 500000, "monthly_attendance_allowance": 1000000, "overtime_hourly_rate": 0,
       "ptkp_status": "TK/0", "join_date": "2024-03-01"}
OKT = {"id": "p10", "start_date": "2026-10-01", "end_date": "2026-10-31"}


def _ctx(initial_pph21, initial_gross=43053400.0, kind="keluar", month=10):
    return {"tax_year": 2026, "has_initial_balance": True, "initial_months": month - 1, "initial_gross": initial_gross,
            "initial_jht_jp": 0.0, "initial_pph21": initial_pph21, "system_gross": 0, "system_jht_jp": 0,
            "system_pph21": 0, "system_months": 0, "kind": kind, "final_month": month}


def _day(status, work_date):
    return integrations.normalize_attendance({
        "work_date": work_date, "status_ham": status, "minutes_late": 0, "minutes_early_leave": 0,
        "is_missing_check_in": False, "is_missing_check_out": False})


def _totals(slip):
    earn, ded = payslip_lines(slip)
    return {l: v for l, v, _ in earn}, {l: v for l, v, _ in ded}


# ---------------------------------------------------------------- 1. lebih bayar -> pendapatan
def test_overpaid_pph21_becomes_income_not_a_negative_deduction():
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(336501.0), OKT)
    assert s["pph21_amount"] == -336501 and s["pph21_refund"] == 336501   # setoran neto tetap bertanda (1721-A1)
    assert s["pph21_withheld"] == 0                                       # yang tampil di tabel/total: tak pernah minus
    assert s["total_deductions"] == (s["iuran_bpjs_kes_total"] + s["iuran_bpjs_tk_total"])   # tak ada PPh minus
    assert s["take_home_pay"] == s["gross_earnings"] + 336501 - s["total_deductions"]
    # tidak masuk bruto: gross_earnings & dasar pajak sama dgn slip tanpa lebih bayar
    plain = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(0.0), OKT)
    assert plain["pph21_refund"] == 0
    assert (s["gross_earnings"], s["taxable_gross"]) == (plain["gross_earnings"], plain["taxable_gross"])
    assert s["take_home_pay"] - plain["take_home_pay"] == 336501


def test_underpaid_pph21_stays_a_deduction():
    # penghasilan Jan–Okt jauh di atas PTKP, belum ada PPh yang dipotong -> kurang bayar
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(0.0, initial_gross=200000000.0), OKT)
    assert s["pph21_amount"] > 0 and s["pph21_refund"] == 0 and s["pph21_withheld"] == s["pph21_amount"]
    assert s["total_deductions"] == s["iuran_bpjs_kes_total"] + s["iuran_bpjs_tk_total"] + s["pph21_amount"]
    assert s["take_home_pay"] == s["gross_earnings"] - s["total_deductions"]


def test_ordinary_month_has_no_refund():
    s = compute_payslip(EMP, [], CFG, {})
    assert s["pph21_method"] == "ter" and s["pph21_refund"] == 0


def test_december_overpayment_is_a_refund_too():
    s = compute_payslip(EMP, [], CFG, {}, _ctx(5000000.0, kind="desember", month=12),
                        {"id": "p12", "start_date": "2026-12-01", "end_date": "2026-12-31"})
    assert s["tax_reconciliation"]["kind"] == "desember" and s["pph21_refund"] > 0
    assert s["pph21_refund"] == -s["pph21_amount"]


def test_payslip_pdf_lists_the_refund_under_pendapatan():
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(336501.0), OKT)
    earn, ded = _totals(s)
    assert earn["Pengembalian Perusahaan"] == 336501
    assert ded["PPh 21 Masa Terakhir (Pasal 17)"] == 0                    # tak ada angka minus di Potongan
    assert all(v >= 0 for v in ded.values())
    # TOTAL PENDAPATAN - TOTAL POTONGAN = TOTAL DITERIMA
    assert earn["TOTAL PENDAPATAN"] - ded["TOTAL POTONGAN"] == s["take_home_pay"]


def test_payslip_pdf_shows_underpayment_as_pph21_deduction_and_no_refund_row():
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(0.0, initial_gross=200000000.0), OKT)
    earn, ded = _totals(s)
    assert "Pengembalian Perusahaan" not in earn
    assert ded["PPh 21 Masa Terakhir (Pasal 17)"] == s["pph21_amount"] > 0
    assert earn["TOTAL PENDAPATAN"] - ded["TOTAL POTONGAN"] == s["take_home_pay"]


def test_legacy_slip_without_refund_field_prints_as_it_was_issued():
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, _ctx(336501.0), OKT)
    legacy = {k: v for k, v in s.items() if k != "pph21_refund"}
    legacy["total_deductions"] = s["total_deductions"] - 336501           # dulu PPh minus ikut total potongan
    earn, ded = _totals(legacy)
    assert "Pengembalian Perusahaan" not in earn
    assert ded["PPh 21 Masa Terakhir (Pasal 17)"] == -336501
    assert earn["TOTAL PENDAPATAN"] - ded["TOTAL POTONGAN"] == s["take_home_pay"]


# ---------------------------------------------------------------- 2. status karyawan aktif / keluar
def test_employment_info_for_hrd():
    left = employment_info(OKT, {**EMP, "exit_date": "2026-10-06"})
    assert left["status"] == "keluar" and left["exit_date"] == "2026-10-06" and left["final_tax"] == "keluar"
    planned = employment_info(OKT, {**EMP, "exit_date": "2026-11-02"})
    assert planned["status"] == "aktif" and planned["exit_planned"] == "2026-11-02" and planned["final_tax"] is None
    active = employment_info(OKT, EMP)
    assert active["status"] == "aktif" and active["exit_date"] is None and active["final_tax"] is None
    dec = employment_info({"start_date": "2026-12-01", "end_date": "2026-12-31"}, EMP)
    assert dec["status"] == "aktif" and dec["final_tax"] == "desember"
    joined = employment_info(OKT, {**EMP, "join_date": "2026-10-12"})
    assert joined["joined_in_period"] is True and active["joined_in_period"] is False


# ---------------------------------------------------------------- 3. cuti melahirkan: Tunjangan Kehadiran Rp 0
def _maternity_month():
    return ([_day("melahirkan", f"2026-10-{d:02d}") for d in range(1, 11)]
            + [_day("libur", "2026-10-04"), _day("libur", "2026-10-11")])


def test_full_period_maternity_pays_zero_attendance_allowance_without_a_cut_row():
    s = compute_payslip(EMP, _maternity_month(), CFG, {})
    assert s["maternity_basic_only"] is True
    assert s["attendance_allowance_base"] == 0 and s["attendance_allowance"] == 0
    assert s["presence_penalty_amount"] == 0 and s["absence_penalty_amount"] == 0 and s["late_penalty_amount"] == 0
    earn, ded = _totals(s)
    assert "Tunjangan Kehadiran" not in earn and "Potongan Presensi" not in ded


def test_full_period_maternity_keeps_attendance_out_of_the_kotor_pph21_basis():
    # basis kotor menambah kembali potongan presensi ke bruto pajak: kehadiran yang tak diberikan tak boleh ikut
    s = compute_payslip(EMP, _maternity_month(), {**CFG, "PPH21_BASIS": "kotor"}, {})
    bp = s["bpjs"]
    assert s["taxable_gross"] == s["basic_salary"] + bp["kes_company"] + bp["jkk"] + bp["jkm"]
    assert s["pph21_addback"] == 0


def test_part_period_maternity_still_prorates_the_attendance_allowance():
    logs = [_day("melahirkan", f"2026-10-{d:02d}") for d in range(1, 15)] + [
        _day("hadir", f"2026-10-{d:02d}") for d in range(15, 32) if d not in (18, 25)] + [
        _day("libur", "2026-10-18"), _day("libur", "2026-10-25")]
    s = compute_payslip(EMP, logs, CFG, {}, None, OKT)
    assert s["maternity_basic_only"] is False
    assert 0 < s["attendance_allowance_base"] < EMP["monthly_attendance_allowance"]
    assert s["position_allowance"] == EMP["position_allowance"]          # jabatan penuh (keputusan HRD 23 Sep)
