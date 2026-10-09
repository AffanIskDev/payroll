"""Contract tests for the HAM payroll feed (api/ham/v2/payroll-feed/*) — pure unit tests, no server.

Fixtures mirror the JSON returned by HAM's PayrollFeedModules (karyawan) and AbsensiModules::harianBatch
(presensi), so a change on either side shows up here first.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

import integrations  # noqa: E402
from engine import calc_bpjs, calc_discipline, compute_payslip, resolve_ptkp  # noqa: E402

HAM_KARYAWAN = {
    "employee_id": "USRD-00683", "nik": "2019012", "ktp": "3216012345678901", "name": "Contoh Karyawan",
    "email": "Contoh@Rumat.co.id", "gender": "P", "birth_date": "1995-08-15", "kawin_raw": "K1",
    "ptkp_status": "TK/0", "npwp": None, "department": "Pelayanan", "position": "Perawat", "level": "Staff",
    "employment_type": "Kontrak", "is_active": True, "join_date": "2024-01-02", "exit_date": None,
    "is_paid": True, "attendance_exempt": False, "user_id_rumatku": "USR-00165", "payroll_company_id": "CP-001",
    "salary": {"basic_salary": 3450000, "position_allowance": 0, "monthly_attendance_allowance": 750000,
               "overtime_hourly_rate": 0},
    "bpjs": {"kes": True, "jkk": True, "jkm": True, "jht": False, "jp": False, "jkk_rate": 0.0024,
             "upah_kes": None, "upah_tk": None},
    "bank": {"name": "BSI", "code": "451", "account_number": "7123456789", "account_name": "CONTOH"},
    "salary_template_id": "TPL-001", "komponen_tetap": [], "data_issues": ["npwp_kosong"],
}

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}


def _harian(status, **kw):
    row = {"employee_id": "USRD-00683", "user_id_rumatku": "USR-00165", "work_date": "2026-09-01",
           "status_ham": status, "hari_kerja": True, "leave_category_id": None, "has_document": None,
           "schedule_start": None, "schedule_end": None, "shift_code": None, "shift_name": None,
           "check_in_time": None, "check_out_time": None, "minutes_late": 0, "minutes_early_leave": 0,
           "is_missing_check_in": False, "is_missing_check_out": False, "excused": False, "ham_points": 0}
    return {**row, **kw}


def test_normalize_employee_keys_on_rosy_id_not_nik():
    e = integrations.normalize_employee(HAM_KARYAWAN)
    assert e["rosy_employee_id"] == "USRD-00683"
    assert e["nik"] == "2019012"
    assert e["email"] == "contoh@rumat.co.id"
    assert e["ptkp_status"] == "TK/0"
    assert e["payroll_status"] == "active"
    assert (e["basic_salary"], e["monthly_attendance_allowance"]) == (3450000.0, 750000.0)
    assert e["bpjs_programs"] == {"kes": True, "jkk": True, "jkm": True, "jht": False, "jp": False}
    assert e["has_bpjs_kes"] and e["has_bpjs_tk"]
    assert e["bank_account_number"] == "7123456789"
    assert e["data_issues"] == ["npwp_kosong"]


def test_placeholder_nik_falls_back_to_rosy_id():
    e = integrations.normalize_employee({**HAM_KARYAWAN, "nik": "-"})
    assert e["nik"] == "USRD-00683"


def test_unpaid_employee_maps_to_unpaid_leave():
    e = integrations.normalize_employee({**HAM_KARYAWAN, "is_paid": False})
    assert e["payroll_status"] == "unpaid_leave"


def test_ptkp_from_ham_wins_over_marital_fields():
    # HAM already applies "married women are TK/0"; the engine must not re-derive it
    assert resolve_ptkp({"ptkp_status": "K/2", "marital_status": "TK", "dependents_count": 0}) == "K/2"
    assert resolve_ptkp({"marital_status": "K", "dependents_count": 1, "gender": "L"}) == "K/1"


@pytest.mark.parametrize("status,expected", [
    ("hadir", "present"), ("dinas", "official_duty"), ("izin", "permission_leave"),
    ("sakit", "sick_with_certificate"), ("cuti", "annual_leave"), ("khusus", "statutory_leave"),
    ("melahirkan", "maternity_leave"), ("ibadah", "religious_leave"), ("alfa", "alpha"),
    ("dispensasi", "dispensation"), ("libur", "day_off"),
])
def test_leave_map_covers_every_ham_status(status, expected):
    assert integrations.normalize_attendance(_harian(status))["leave_type"] == expected


def test_unknown_ham_status_fails_loudly():
    with pytest.raises(ValueError):
        integrations.normalize_attendance(_harian("bolos"))


def test_sick_without_document_is_flagged():
    row = integrations.normalize_attendance(_harian("sakit", has_document=False))
    assert row["leave_type"] == "sick_with_certificate"
    assert "tanpa lampiran" in row["notes"]


def test_official_duty_and_permission_rules():
    logs = [integrations.normalize_attendance(_harian("dinas", minutes_late=90)),
            integrations.normalize_attendance(_harian("izin", work_date="2026-09-02"))]
    disc = calc_discipline(logs)
    # dinas: never penalised even with check-in minutes; izin (PPT): unpaid like alfa — attendance, gapok, jabatan
    assert disc["total_points"] == 0
    assert disc["attendance_cut_days"] == 1
    assert disc["basic_cut_days"] == 1


def test_attendance_exempt_employee_has_no_penalty():
    emp = integrations.normalize_employee({**HAM_KARYAWAN, "attendance_exempt": True})
    logs = [integrations.normalize_attendance(_harian("alfa"))]
    slip = compute_payslip(emp, logs, CFG, {})
    assert slip["late_penalty_amount"] == 0
    assert slip["absent_deduction_amount"] == 0


def test_absent_deduction_never_exceeds_basic_salary():
    emp = integrations.normalize_employee(HAM_KARYAWAN)
    logs = [integrations.normalize_attendance(_harian("alfa", work_date=f"2026-09-{d:02d}")) for d in range(1, 27)]
    slip = compute_payslip(emp, logs, CFG, {})
    assert slip["absent_days"] == 26
    assert slip["absent_deduction_amount"] == emp["basic_salary"]


def test_bpjs_follows_per_program_membership():
    emp = integrations.normalize_employee(HAM_KARYAWAN)
    b = calc_bpjs(emp, CFG)
    assert b["kes_company"] > 0 and b["jkk"] > 0 and b["jkm"] > 0
    assert b["jht_company"] == b["jht_employee"] == 0
    assert b["jp_company"] == b["jp_employee"] == 0


def test_mock_mode_keeps_same_employee_shape(monkeypatch):
    monkeypatch.delenv("HAM_API_URL", raising=False)
    assert integrations.mode("ROSY") == "mock"
    rows = [integrations.normalize_employee(r) for r in integrations._mock_rosy()]
    budi = next(r for r in rows if r["nik"] == "EMP-001")
    assert budi["rosy_employee_id"] == "MOCK-EMP-001"
    assert budi["ptkp_status"] == "K/1"
    assert next(r for r in rows if r["nik"] == "EMP-003")["payroll_status"] == "unpaid_leave"


def test_live_mode_switches_on_ham_url(monkeypatch):
    monkeypatch.setenv("HAM_API_URL", "http://127.0.0.1:8601")
    assert integrations.mode("ROSY") == integrations.mode("RUMATKU") == "live"


HAM_LEMBUR = {"status": 200, "data": [
    {"claim_id": 2, "employee_id": "USRD-00015", "user_id_rumatku": "USR-00062", "tanggal": "2026-09-29",
     "jam_mulai": "2026-09-29 17:00:00", "jam_selesai": "2026-09-29 21:00:00", "menit_diklaim": 240,
     "menit_disetujui": 240, "periode_bayar": "2026-10", "approved_at": "2026-10-08 09:00:00"},
    {"claim_id": 4, "employee_id": "USRD-00015", "user_id_rumatku": "USR-00062", "tanggal": "2026-10-02",
     "jam_mulai": "2026-10-02 06:00:00", "jam_selesai": "2026-10-02 07:00:00", "menit_diklaim": 60,
     "menit_disetujui": 60, "periode_bayar": "2026-10", "approved_at": None},
], "meta": {"periode_bayar": "2026-10", "menunggu": 1, "tanpa_tarif": []}}


def test_overtime_stays_in_daily_logs_in_mock_mode(monkeypatch):
    import asyncio
    monkeypatch.delenv("HAM_API_URL", raising=False)
    assert asyncio.run(integrations.fetch_overtime("2026-10")) is None


def test_overtime_claims_are_read_by_pay_month_in_live_mode(monkeypatch):
    import asyncio
    monkeypatch.setenv("HAM_API_URL", "http://ham.test")
    calls = []

    async def fake_get(path, params):
        calls.append((path, params))
        return HAM_LEMBUR

    monkeypatch.setattr(integrations, "_get", fake_get)
    claims, meta = asyncio.run(integrations.fetch_overtime("2026-10"))
    assert calls == [("/lembur", {"payroll_company_id": "CP-001", "periode_bayar": "2026-10"})]
    # a claim dated in September but approved late is still paid in the October slip
    assert [c["tanggal"] for c in claims] == ["2026-09-29", "2026-10-02"]
    assert sum(c["menit_disetujui"] for c in claims) == 300
    assert meta["menunggu"] == 1


@pytest.mark.parametrize("hours,rate,expected", [(4.5, 25000, 112500), (6.5, 30000, 195000), (4.0, 35000, 140000)])
def test_overtime_pay_matches_ham_formula(hours, rate, expected):
    # HAM LemburGajiModules: round(menit / 60 x tarif per jam) — Adit's sample expectations for October 2026
    emp = integrations.normalize_employee({**HAM_KARYAWAN, "salary": {**HAM_KARYAWAN["salary"], "overtime_hourly_rate": rate}})
    assert compute_payslip(emp, [], CFG, {"overtime_hours": hours})["overtime_pay"] == expected
