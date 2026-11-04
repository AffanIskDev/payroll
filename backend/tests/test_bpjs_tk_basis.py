"""Dasar BPJS Ketenagakerjaan (user 1 Nov 2026): config BPJS_TK_BASIS = "formula" (bawaan) | "import".

import  = JKK / JKM / JHT / JP tiap orang dari data given BPJS (emp["bpjs_tk_given"]); orang tanpa data given, dan kolom yang
          kosong di datanya, tetap memakai rumus;
formula = persentase dari gaji pokok, JP dibatasi BPJS_JP_MAX_WAGE (aturan RUSA sebelum setelan ini ada).
Tanpa server dan tanpa database."""
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

from core import CONFIG_CHOICES, DEFAULT_CONFIGS  # noqa: E402
from engine import bpjs_tk_basis, calc_bpjs, compute_payslip  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5938880", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000", "DEFAULT_WORK_DAYS": "25",
       "BPJS_KES_BASIS": "flat_umk"}
IMPORT = {**CFG, "BPJS_TK_BASIS": "import"}
FORMULA = {**CFG, "BPJS_TK_BASIS": "formula"}
# Fakhrudin, Okt 2026: gaji pokok 90 jt, upah terdaftar di BPJS 30 jt, JP dasar 11.086.300 (data given BPJS)
GIVEN = {"upah_tk": 30000000, "jkk": 72000, "jkm": 90000, "jht_company": 1110000, "jht_employee": 600000,
         "jp_base": 11086300, "jp_company": 221726, "jp_employee": 110863}


def _emp(basic=90000000, given=None, programs=None):
    e = {"payroll_status": "active", "basic_salary": basic, "position_allowance": 0, "monthly_attendance_allowance": 1000000,
         "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}
    if given is not None:
        e["bpjs_tk_given"] = given
    if programs is not None:
        e["bpjs_programs"] = programs
    return e


@pytest.mark.parametrize("cfg,expected", [
    (None, "formula"), ({}, "formula"), ({"BPJS_TK_BASIS": ""}, "formula"), ({"BPJS_TK_BASIS": "imprt"}, "formula"),  # typo = rumus lama
    ({"BPJS_TK_BASIS": "formula"}, "formula"), ({"BPJS_TK_BASIS": "import"}, "import"), ({"BPJS_TK_BASIS": " IMPORT "}, "import"),
])
def test_the_basis_is_read_from_the_config(cfg, expected):
    assert bpjs_tk_basis(cfg) == expected


def test_the_setting_is_seeded_as_formula_and_only_accepts_its_two_values():
    assert DEFAULT_CONFIGS["BPJS_TK_BASIS"][0] == "formula"   # tanpa data given, tidak ada yang berubah
    assert CONFIG_CHOICES["BPJS_TK_BASIS"] == ("import", "formula")


def test_import_uses_the_given_amounts_not_the_percentages_of_gapok():
    b = calc_bpjs(_emp(given=GIVEN), IMPORT)
    assert (b["jkk"], b["jkm"], b["jht_company"], b["jht_employee"]) == (72000, 90000, 1110000, 600000)
    assert (b["jp_base"], b["jp_company"], b["jp_employee"]) == (11086300, 221726, 110863)


def test_formula_ignores_a_given_record_it_is_only_used_in_import_mode():
    b = calc_bpjs(_emp(given=GIVEN), FORMULA)
    assert b["jht_company"] == round(90000000 * 0.037) and b["jp_base"] == 10042300
    assert calc_bpjs(_emp(given=GIVEN), CFG) == b          # setelan belum ada = formula


def test_import_mode_without_a_record_for_the_person_falls_back_to_the_formula():
    assert calc_bpjs(_emp(), IMPORT) == calc_bpjs(_emp(), FORMULA)
    assert calc_bpjs(_emp(given=None), IMPORT) == calc_bpjs(_emp(), FORMULA)


def test_a_field_the_record_does_not_have_uses_the_formula_for_that_field_only():
    b = calc_bpjs(_emp(basic=5000000, given={"jht_company": 100, "jht_employee": 50}), IMPORT)
    assert (b["jht_company"], b["jht_employee"]) == (100, 50)
    assert b["jkk"] == round(5000000 * 0.0024) and b["jp_company"] == round(5000000 * 0.02)


def test_a_given_zero_is_respected_not_replaced_by_the_formula():
    b = calc_bpjs(_emp(basic=5000000, given={**GIVEN, "jkk": 0}), IMPORT)
    assert b["jkk"] == 0


def test_programs_the_person_has_not_joined_stay_zero_even_with_a_record():
    b = calc_bpjs(_emp(given=GIVEN, programs={"kes": True, "jkk": True, "jkm": True, "jht": False, "jp": False}), IMPORT)
    assert b["jht_company"] == b["jht_employee"] == b["jp_company"] == b["jp_employee"] == b["jp_base"] == 0
    assert b["jkk"] == 72000 and b["jkm"] == 90000


def test_kes_is_independent_of_the_tk_basis():
    assert calc_bpjs(_emp(given=GIVEN), IMPORT)["kes_company"] == calc_bpjs(_emp(given=GIVEN), FORMULA)["kes_company"] == 237555


def test_the_slip_totals_and_pph21_gross_follow_the_given_amounts():
    imp = compute_payslip(_emp(given=GIVEN), [], IMPORT, {})
    frm = compute_payslip(_emp(), [], FORMULA, {})
    assert imp["tunjangan_bpjs_tk"] == 72000 + 90000 + 1110000 + 221726
    assert imp["iuran_bpjs_tk_total"] == 72000 + 90000 + 1110000 + 600000 + 221726 + 110863
    # JKK + JKM porsi perusahaan masuk bruto pajak (JHT/JP tidak), jadi bruto pajak ikut berubah persis selisih itu
    d_jkk_jkm = (round(90000000 * 0.0024) + round(90000000 * 0.003)) - (72000 + 90000)
    assert frm["taxable_gross"] - imp["taxable_gross"] == d_jkk_jkm
    assert imp["take_home_pay"] - frm["take_home_pay"] != 0


def test_unpaid_person_still_pays_nothing_in_import_mode():
    e = {**_emp(given=GIVEN), "payroll_status": "unpaid_leave"}
    s = compute_payslip(e, [], IMPORT, {})
    assert s["tunjangan_bpjs_tk"] == 0 and s["iuran_bpjs_tk_total"] == 0


# ----------------------------------------------------------------------------------- impor berkas (tanpa database)
def test_the_upload_reader_accepts_csv_with_the_template_columns():
    from routes_bpjs_tk import COLUMNS, AMOUNTS
    from routes_tax import _rows_from_upload
    csv_text = ",".join(COLUMNS) + "\n2010002,FAKHRUDIN,30000000,72000,90000,1110000,600000,11086300,221726,110863\n"
    rows = _rows_from_upload("x.csv", csv_text.encode())
    assert rows[0]["nik"] == "2010002" and set(AMOUNTS) <= set(rows[0])
