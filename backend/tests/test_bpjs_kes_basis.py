"""Dasar BPJS Kesehatan (user 1 Nov 2026): config BPJS_KES_BASIS = "flat_umk" (bawaan baru) | "formula".

flat_umk = semua karyawan memakai nilai UMK (UMK_BEKASI_REGENCY), berapa pun gaji pokoknya;
formula  = yang terbesar antara gaji pokok dan UMK, maksimal BPJS_KES_MAX_WAGE (aturan RUSA sebelum setelan ini ada).
Tanpa server dan tanpa database."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

from core import CONFIG_CHOICES, DEFAULT_CONFIGS  # noqa: E402
from engine import bpjs_kes_basis, calc_bpjs, compute_payslip  # noqa: E402

UMK = "5938880"
CFG = {"UMK_BEKASI_REGENCY": UMK, "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000", "DEFAULT_WORK_DAYS": "25"}
FLAT = {**CFG, "BPJS_KES_BASIS": "flat_umk"}
FORMULA = {**CFG, "BPJS_KES_BASIS": "formula"}


def _emp(basic):
    return {"payroll_status": "active", "basic_salary": basic, "position_allowance": 0, "monthly_attendance_allowance": 1000000,
            "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}


@pytest.mark.parametrize("cfg,expected", [
    (None, "formula"), ({}, "formula"), ({"BPJS_KES_BASIS": ""}, "formula"), ({"BPJS_KES_BASIS": "flat"}, "formula"),  # typo = rumus lama
    ({"BPJS_KES_BASIS": "formula"}, "formula"), ({"BPJS_KES_BASIS": "flat_umk"}, "flat_umk"), ({"BPJS_KES_BASIS": " FLAT_UMK "}, "flat_umk"),
])
def test_the_basis_is_read_from_the_config(cfg, expected):
    assert bpjs_kes_basis(cfg) == expected


def test_the_setting_is_seeded_as_flat_umk_and_only_accepts_its_two_values():
    assert DEFAULT_CONFIGS["BPJS_KES_BASIS"][0] == "flat_umk"
    assert CONFIG_CHOICES["BPJS_KES_BASIS"] == ("flat_umk", "formula")


@pytest.mark.parametrize("basic", [2000000, 5938880, 8000000, 15000000])
def test_flat_umk_gives_every_employee_the_umk_regardless_of_gapok(basic):
    b = calc_bpjs(_emp(basic), FLAT)
    assert b["kes_base"] == 5938880
    assert b["kes_company"] == 237555 and b["kes_employee"] == 59389        # 4% / 1% of 5.938.880


@pytest.mark.parametrize("basic,base", [(2000000, 5938880), (8000000, 8000000), (15000000, 12000000)])
def test_formula_keeps_the_old_rule_max_of_gapok_and_umk_with_the_cap(basic, base):
    b = calc_bpjs(_emp(basic), FORMULA)
    assert b["kes_base"] == base


def test_flat_umk_only_touches_bpjs_kesehatan():
    emp = _emp(8000000)
    flat, formula = calc_bpjs(emp, FLAT), calc_bpjs(emp, FORMULA)
    for k in ("jkk", "jkm", "jht_company", "jht_employee", "jp_base", "jp_company", "jp_employee"):
        assert flat[k] == formula[k], k


def test_an_employee_outside_bpjs_kes_stays_at_zero_in_both_modes():
    emp = {**_emp(8000000), "bpjs_programs": {"kes": False}}
    assert calc_bpjs(emp, FLAT)["kes_company"] == 0 and calc_bpjs(emp, FORMULA)["kes_company"] == 0


def test_the_slip_and_the_pph21_gross_follow_the_basis():
    emp = _emp(8000000)
    flat = compute_payslip(emp, [], FLAT, {})
    formula = compute_payslip(emp, [], FORMULA, {})
    assert flat["tunjangan_bpjs_kes"] == 237555 and formula["tunjangan_bpjs_kes"] == 320000   # 4% of 8.000.000
    # porsi perusahaan masuk bruto pajak, jadi bruto flat lebih kecil persis selisih itu
    assert formula["taxable_gross"] - flat["taxable_gross"] == 320000 - 237555
    assert flat["iuran_bpjs_kes_total"] == 237555 + 59389
