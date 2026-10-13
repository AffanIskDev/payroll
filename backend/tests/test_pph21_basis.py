"""PPh 21 basis (user 13 Oct 2026): config PPH21_BASIS = "bersih" (default) | "kotor".

bersih = the income left after Potongan Presensi & Absensi (the basis RASA used before the setting existed);
kotor  = the income before those cuts, so a gapok / jabatan / kehadiran cut for absence still counts as bruto.
The engine tests need no server and no database; the 1721-A1 and the config save run against a throwaway MongoDB that
is dropped afterwards (skipped when MongoDB is not running)."""
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import integrations  # noqa: E402
from core import CONFIG_CHOICES, DEFAULT_CONFIGS  # noqa: E402
from engine import compute_payslip, pph21_basis  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
KOTOR = {**CFG, "PPH21_BASIS": "kotor"}
# gapok 4.5 jt, jabatan 500 rb, kehadiran 750 rb, 25 work days: one alfa day cuts 180 rb + 20 rb + 30 rb
EMP = {"payroll_status": "active", "basic_salary": 4500000, "position_allowance": 500000,
       "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}


def _day(status, date="2026-10-01", **kw):
    row = {"work_date": date, "status_ham": status, "minutes_late": 0, "minutes_early_leave": 0,
           "is_missing_check_in": False, "is_missing_check_out": False}
    return integrations.normalize_attendance({**row, **kw})


# one alfa day, one cuti day (cuts only the attendance allowance) and a 75-minute lateness
MIXED = [_day("hadir", "2026-10-01", minutes_late=75), _day("cuti", "2026-10-02"), _day("alfa", "2026-10-03")]


def _cuts(slip):
    return (slip["presence_penalty_amount"] + slip["absence_penalty_amount"] + slip["absent_deduction_amount"]
            + slip["position_deduction_amount"])


# ---------------------------------------------------------------- the setting itself
@pytest.mark.parametrize("cfg,expected", [
    (None, "bersih"), ({}, "bersih"), ({"PPH21_BASIS": "bersih"}, "bersih"), ({"PPH21_BASIS": ""}, "bersih"),
    ({"PPH21_BASIS": "gross"}, "bersih"),                       # a typo never switches the tax basis
    ({"PPH21_BASIS": "kotor"}, "kotor"), ({"PPH21_BASIS": " KOTOR "}, "kotor"),
])
def test_the_basis_is_read_from_the_config_and_defaults_to_bersih(cfg, expected):
    assert pph21_basis(cfg) == expected


def test_the_setting_is_seeded_as_bersih_and_only_accepts_its_two_values():
    assert DEFAULT_CONFIGS["PPH21_BASIS"][0] == "bersih"
    assert CONFIG_CHOICES["PPH21_BASIS"] == ("bersih", "kotor")


# ---------------------------------------------------------------- engine
def test_bersih_is_what_the_engine_always_did():
    base = compute_payslip(EMP, MIXED, CFG, {})
    explicit = compute_payslip(EMP, MIXED, {**CFG, "PPH21_BASIS": "bersih"}, {})
    assert explicit == base
    assert (base["pph21_basis"], base["pph21_addback"]) == ("bersih", 0)
    # review page: Bruto Objek Pajak = Total Pendapatan (before the cuts) − Potongan Presensi & Absensi − JHT & JP perusahaan
    bp = base["bpjs"]
    assert base["taxable_gross"] == base["gross_earnings"] - bp["jht_company"] - bp["jp_company"]


def test_kotor_adds_back_exactly_the_attendance_cuts():
    b = compute_payslip(EMP, MIXED, CFG, {})
    k = compute_payslip(EMP, MIXED, KOTOR, {})
    cuts = _cuts(b)
    assert cuts == 290000 and k["taxable_gross"] - b["taxable_gross"] == cuts
    assert (k["pph21_basis"], k["pph21_addback"]) == ("kotor", cuts)
    # the same formula the page shows: Total Pendapatan − JHT & JP perusahaan (the cuts do not reduce it)
    total_pendapatan = k["gross_earnings"] + k["presence_penalty_amount"] + (
        k["absence_penalty_amount"] + k["absent_deduction_amount"] + k["position_deduction_amount"])
    assert k["taxable_gross"] == total_pendapatan - k["bpjs"]["jht_company"] - k["bpjs"]["jp_company"]
    # nothing but the PPh 21 moves: income, BPJS and the cuts themselves stay as they were
    for key in ("gross_earnings", "iuran_bpjs_kes_total", "iuran_bpjs_tk_total", "bpjs",
                "presence_penalty_amount", "absence_penalty_amount", "absent_deduction_amount",
                "position_deduction_amount", "attendance_allowance", "basic_salary", "position_allowance"):
        assert k[key] == b[key], key
    more_pph21 = k["pph21_amount"] - b["pph21_amount"]
    assert more_pph21 > 0
    assert k["total_deductions"] - b["total_deductions"] == more_pph21
    assert b["take_home_pay"] - k["take_home_pay"] == more_pph21


def test_one_alfa_day_pinned():
    b = compute_payslip(EMP, [_day("alfa")], CFG, {})
    k = compute_payslip(EMP, [_day("alfa")], KOTOR, {})
    assert _cuts(b) == 180000 + 20000 + 30000
    assert (b["taxable_gross"], b["ter_rate"], b["pph21_amount"]) == (5753071, 0.5, 28765)
    assert (k["taxable_gross"], k["ter_rate"], k["pph21_amount"]) == (5983071, 0.75, 44873)   # the full month's bruto
    assert compute_payslip(EMP, [], CFG, {})["taxable_gross"] == k["taxable_gross"]


def test_kotor_changes_nothing_without_attendance_cuts():
    for logs in ([], [_day("hadir")], [_day("dinas")], [_day("dispensasi")]):
        assert compute_payslip(EMP, logs, KOTOR, {}) == {**compute_payslip(EMP, logs, CFG, {}), "pph21_basis": "kotor"}


@pytest.mark.parametrize("status", ["unpaid_leave", "prolonged_illness", "work_accident_stmb"])
def test_kotor_taxes_no_income_that_is_not_paid(status):
    # these statuses do not earn the attendance allowance at all — it is not a "cut", so nothing is added back
    emp = {**EMP, "payroll_status": status, "prolonged_illness_month_count": 6}
    b, k = compute_payslip(emp, MIXED, CFG, {}), compute_payslip(emp, MIXED, KOTOR, {})
    assert k["pph21_addback"] == 0
    assert (k["taxable_gross"], k["pph21_amount"]) == (b["taxable_gross"], b["pph21_amount"])


def test_a_month_of_alfa_is_taxed_on_the_contract_pay_not_beyond_it():
    logs = [_day("alfa", f"2026-10-{d:02d}") for d in range(1, 31)]
    b, k = compute_payslip(EMP, logs, CFG, {}), compute_payslip(EMP, logs, KOTOR, {})
    bp = k["bpjs"]
    contract = 4500000 + 500000 + 750000 + bp["kes_company"] + bp["jkk"] + bp["jkm"]
    assert k["taxable_gross"] == contract                       # cuts are capped at 100%, so is the add-back
    assert b["taxable_gross"] == bp["kes_company"] + bp["jkk"] + bp["jkm"]


def test_kotor_feeds_the_december_reconciliation():
    ctx = {"tax_year": 2026, "has_initial_balance": False, "initial_months": 0, "initial_gross": 0.0,
           "initial_jht_jp": 0.0, "initial_pph21": 0.0, "system_gross": 60000000.0, "system_jht_jp": 1000000.0,
           "system_pph21": 400000.0, "system_months": 11}
    b = compute_payslip(EMP, MIXED, CFG, {}, ctx)
    k = compute_payslip(EMP, MIXED, KOTOR, {}, ctx)
    assert b["tax_reconciliation"]["december_gross"] == b["taxable_gross"]
    assert k["tax_reconciliation"]["december_gross"] == k["taxable_gross"] == b["taxable_gross"] + 290000
    assert k["tax_reconciliation"]["gross_year"] - b["tax_reconciliation"]["gross_year"] == 290000
    assert k["pph21_method"] == "pasal17" and k["pph21_basis"] == "kotor"


# ---------------------------------------------------------------- MongoDB: 1721-A1 and the config save
def _with_throwaway_db(coro_fn):
    from motor.motor_asyncio import AsyncIOMotorClient

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        name = f"rasa_test_pph21_{uuid.uuid4().hex[:8]}"
        try:
            await coro_fn(client[name])
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_1721a1_reports_the_income_each_slip_was_taxed_on(monkeypatch):
    import tax_forms

    async def body(tdb):
        monkeypatch.setattr(tax_forms, "db", tdb)
        legacy = compute_payslip(EMP, MIXED, CFG, {})
        for f in ("pph21_basis", "pph21_addback"):
            legacy.pop(f)                                       # a slip approved before the setting existed
        slips = {1: compute_payslip(EMP, MIXED, CFG, {}), 2: compute_payslip(EMP, MIXED, KOTOR, {}), 3: legacy}
        for m, slip in slips.items():
            pid = f"p{m}"
            await tdb.payroll_periods.insert_one({"id": pid, "start_date": f"2027-{m:02d}-01", "end_date": f"2027-{m:02d}-28"})
            await tdb.payslips.insert_one({**slip, "payroll_period_id": pid, "employee_id": "e1", "status": "approved"})
        a1 = await tax_forms.build_1721a1({**EMP, "id": "e1", "nik": "1", "name": "X"}, 2027, 1)
        it = a1["items"]
        # angka 8 = exactly what the three slips were taxed on (so the form's annual tax matches the PPh 21 withheld)
        assert it["i8"] == sum(s["taxable_gross"] for s in slips.values())
        # only the kotor slip reports its cuts: gapok / jabatan / kehadiran go back into angka 1 and 3
        only_bersih = compute_payslip(EMP, MIXED, CFG, {})
        assert it["i8"] - 3 * only_bersih["taxable_gross"] == slips[2]["pph21_addback"] == 290000

    _with_throwaway_db(body)


def test_config_save_validates_the_choice_and_lists_it(monkeypatch):
    import routes_hr

    async def body(tdb):
        monkeypatch.setattr(routes_hr, "db", tdb)
        for k, (v, desc) in DEFAULT_CONFIGS.items():
            await tdb.payroll_configs.insert_one({"config_key": k, "config_value": v, "description": desc})
        listed = {c["config_key"]: c for c in await routes_hr.list_configs()}
        assert listed["PPH21_BASIS"]["choices"] == ["bersih", "kotor"] and listed["PPH21_BASIS"]["config_value"] == "bersih"
        assert "choices" not in listed["DEFAULT_WORK_DAYS"]       # free-text configs stay free text
        saved = {c["config_key"]: c for c in await routes_hr.update_configs({"PPH21_BASIS": "kotor"})}
        assert saved["PPH21_BASIS"]["config_value"] == "kotor"
        with pytest.raises(HTTPException) as err:
            await routes_hr.update_configs({"PPH21_BASIS": "gross"})
        assert err.value.status_code == 400
        assert (await tdb.payroll_configs.find_one({"config_key": "PPH21_BASIS"}))["config_value"] == "kotor"

    _with_throwaway_db(body)
