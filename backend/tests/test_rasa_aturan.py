"""RASA rules of 9 Oct 2026 — pure unit tests, no server, no database.

Access from the ROSY position, one period per month with an automatic name, the PPT absence matrix,
Transport Homecare, and the new payslip layout."""
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pypdf import PdfReader  # noqa: E402

import integrations  # noqa: E402
from access import role_for  # noqa: E402
from engine import calc_discipline, compute_payslip  # noqa: E402
from pdf_service import payslip_lines, render_payslip  # noqa: E402
from periods import overlaps, payroll_month, period_name_for, validate_dates  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"payroll_status": "active", "basic_salary": 4500000, "position_allowance": 500000,
       "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}


def _pos(nama, level, dept):
    return {"position_id": "PST-X", "nama": nama, "level": level, "department_id": dept, "department": "-"}


# ---------------------------------------------------------------- access (facts as HAM returns them, 9 Oct)
@pytest.mark.parametrize("jabatan,expected", [
    ([_pos("General Manager", "General Manager", "DEP-0008")], "manager_hrd"),       # Meliawasni
    ([_pos("Manajer HRD", "Manager", "DEP-0001")], "manager_hrd"),
    ([_pos("Supervisor HRD", "Koordinator", "DEP-0001")], "supervisor"),             # Alvia
    ([_pos("Supervisor Klinik", "Koordinator", "DEP-0001")], None),
    ([_pos("Supervisor Diklat", "Koordinator", "DEP-0001")], None),
    ([_pos("Staff Personalia", "Staff", "DEP-0001")], None),
    ([_pos("Direktur", "Director", "DEP-0008")], None),
    ([_pos("Staff IT Support", "Staff", "DEP-0007")], None),
    ([_pos("Supervisor HRD", "Koordinator", "DEP-0002")], None),                      # HRD name, other dept
    ([], None), (None, None),
])
def test_access_follows_rosy_position(jabatan, expected):
    assert role_for(jabatan) == expected


def test_access_takes_the_highest_role_and_ignores_case():
    jabatan = [_pos("supervisor hrd", "KOORDINATOR", "dep-0001"), _pos("Manajer  HRD", "manager", "DEP-0001")]
    assert role_for(jabatan) == "manager_hrd"


def test_access_department_comes_from_env(monkeypatch):
    monkeypatch.setenv("RASA_DEPT_HAM", "DEP-0099")
    assert role_for([_pos("Supervisor HRD", "Koordinator", "DEP-0001")]) is None
    assert role_for([_pos("Supervisor HRD", "Koordinator", "DEP-0099")]) == "supervisor"


# ---------------------------------------------------------------- periods
def test_period_name_is_automatic_within_one_month():
    assert period_name_for("2026-10-01", "2026-10-31") == "Oktober 2026"
    assert period_name_for("2026-01-05", "2026-01-25") == "Januari 2026"
    assert period_name_for("2026-09-26", "2026-10-25") is None
    assert payroll_month("2026-10-01") == "2026-10"


@pytest.mark.parametrize("start,end", [("2026-10-31", "2026-10-01"), ("2026-10-01", "2026-11-05"),
                                       ("01-10-2026", "2026-10-31")])
def test_invalid_period_dates_are_refused(start, end):
    with pytest.raises(HTTPException) as e:
        validate_dates(start, end)
    assert e.value.status_code == 400


def test_period_overlap():
    sep = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    assert overlaps("2026-09-15", "2026-10-14", sep)
    assert not overlaps("2026-10-01", "2026-10-31", sep)


# ---------------------------------------------------------------- PPT absence matrix
def _day(status, **kw):
    row = {"work_date": "2026-10-01", "status_ham": status, "minutes_late": 0, "minutes_early_leave": 0,
           "is_missing_check_in": False, "is_missing_check_out": False}
    return integrations.normalize_attendance({**row, **kw})


# one day of each HAM status for EMP (gapok 4.5 jt, jabatan 500 rb, kehadiran 750 rb, wd 25):
# (gapok cut, jabatan cut, kehadiran cut)
@pytest.mark.parametrize("status,cuts", [
    ("alfa", (180000, 20000, 30000)), ("izin", (180000, 20000, 30000)),
    ("cuti", (0, 0, 30000)), ("sakit", (0, 0, 30000)), ("khusus", (0, 0, 30000)),
    ("melahirkan", (0, 0, 30000)), ("ibadah", (0, 0, 30000)),
    ("dinas", (0, 0, 0)), ("dispensasi", (0, 0, 0)), ("libur", (0, 0, 0)), ("hadir", (0, 0, 0)),
])
def test_ppt_matrix(status, cuts):
    slip = compute_payslip(EMP, [_day(status)], CFG, {})
    assert (slip["absent_deduction_amount"], slip["position_deduction_amount"], slip["late_penalty_amount"]) == cuts


def test_dispensasi_correction_row_earns_no_presence_point():
    # HAM marks correction rows without a check-in; dispensasi is excused, never a Rule-1 point
    slip = compute_payslip(EMP, [_day("dispensasi", is_missing_check_in=True)], CFG, {})
    assert slip["late_penalty_points"] == 0 and slip["late_penalty_amount"] == 0


def test_poin_presensi_and_poin_absensi_are_separate():
    logs = [_day("hadir", minutes_late=75), _day("cuti", work_date="2026-10-02"),
            _day("izin", work_date="2026-10-03")]
    disc = calc_discipline(logs)
    assert disc["total_points"] == 1                     # Poin Presensi: late >= 60 min
    assert disc["absence_points"] == 2                   # Poin Absensi: cuti + izin
    assert disc["absence_by_type"] == {"annual_leave": 1, "permission_leave": 1}
    slip = compute_payslip(EMP, logs, CFG, {})
    assert slip["late_penalty_amount"] == 3 * 30000     # (1 + 2) / 25 of the attendance allowance


def test_a_month_of_alfa_never_exceeds_100_percent():
    logs = [_day("alfa", work_date=f"2026-10-{d:02d}") for d in range(1, 31)]
    slip = compute_payslip(EMP, logs, CFG, {})
    assert slip["absent_deduction_amount"] == EMP["basic_salary"]
    assert slip["position_deduction_amount"] == EMP["position_allowance"]
    assert slip["attendance_allowance"] == 0


@pytest.mark.parametrize("month,rate", [(1, 1.0), (4, 1.0), (5, 0.75), (8, 0.75), (9, 0.5), (12, 0.5), (13, 0.25)])
def test_prolonged_illness_pays_gapok_bands_only(month, rate):
    emp = {**EMP, "payroll_status": "prolonged_illness", "prolonged_illness_month_count": month}
    slip = compute_payslip(emp, [], CFG, {})
    assert slip["basic_salary"] == round(EMP["basic_salary"] * rate)
    assert slip["position_allowance"] == 0 and slip["attendance_allowance"] == 0


# ---------------------------------------------------------------- Transport Homecare & Kompensasi
def test_transport_homecare_is_taxable_income():
    base = compute_payslip(EMP, [], CFG, {})
    slip = compute_payslip(EMP, [], CFG, {"transport_homecare": 1250000})
    assert slip["transport_homecare"] == 1250000
    assert slip["gross_earnings"] - base["gross_earnings"] == 1250000
    assert slip["taxable_gross"] - base["taxable_gross"] == 1250000
    assert slip["take_home_pay"] - base["take_home_pay"] == 1250000 - (slip["pph21_amount"] - base["pph21_amount"])


def test_unpaid_leave_gets_no_transport():
    slip = compute_payslip({**EMP, "payroll_status": "unpaid_leave"}, [], CFG, {"transport_homecare": 500000})
    assert slip["transport_homecare"] == 0


def test_kompensasi_denda_is_gone():
    slip = compute_payslip(EMP, [_day("hadir", minutes_late=75)], CFG, {"late_penalty_compensation": 30000})
    assert "late_penalty_compensation" not in slip
    assert slip["attendance_allowance"] == 750000 - 30000


def test_transport_is_read_from_rosy_monthly_components():
    row = {"komponen_bulanan": [{"component_id": "KOMP-00022", "nama": "Transport Rumat Kita", "tipe": "pendapatan",
                                 "nominal": 1350000.0},
                                {"component_id": "KOMP-00023", "nama": "Lembur", "tipe": "pendapatan", "nominal": 90000.0},
                                {"component_id": "KOMP-00005", "nama": "Bonus", "tipe": "pendapatan", "nominal": 50000.0}]}
    assert integrations.transport_of(row) == 1350000.0  # Lembur is paid from HAM claims, never twice
    assert integrations.transport_of({}) == 0


# ---------------------------------------------------------------- payslip PDF
SIGNER = {"id": "SIGN-00001", "nama": "Meliawasni", "jabatan": "Manager HRD"}  # ROSY Document Signer (payroll)


def _slip(**kw):
    s = compute_payslip(EMP, [_day("izin")], CFG, {"transport_homecare": 1250000})
    s["employee"] = {"nik": "2016008", "name": "Contoh Karyawan", "department": "Perawat",
                     "bank_name": "Bank Syariah Indonesia", "bank_code": "bsi", "bank_account_number": "7123456789",
                     "birth_date": "1995-01-01"}
    s.update(kw)
    return s


def _pdf(slip):
    reader = PdfReader(io.BytesIO(render_payslip(slip, {"period_name": "Oktober 2026", "signer": SIGNER})))
    page = reader.pages[0]
    images = [o for o in page["/Resources"]["/XObject"].values() if o.get_object()["/Subtype"] == "/Image"]
    return page.extract_text(), len(images)


def test_payslip_layout():
    text, images = _pdf(_slip())
    assert images == 2                                            # RPI left, RUMAT right
    for label in ("Nama:", "NIK:", "Departemen:", "Periode:", "Status PTKP:", "Rekening:", "7123456789 (BSI)",
                  "TOTAL DITERIMA", "Transport Homecare", "Potongan Gaji Pokok (1 hari alfa/izin)",
                  "Potongan Tunj. Jabatan (1 hari alfa/izin)", "menghubungi Divisi HRD"):
        assert label in text, label
    assert "PENDAPATAN" in text and "TOTAL PENDAPATAN" in text
    for gone in ("Status PTKP Efektif", "TAKE HOME PAY", "Kompensasi", "[NAMA_PERUSAHAAN]", "[NAMA_PENANDATANGAN]",
                 "PENERIMAAN"):
        assert gone not in text, gone


def test_payslip_signer_comes_from_rosy():
    text, _ = _pdf(_slip())
    assert "Meliawasni" in text and "Manager HRD" in text


def test_payslip_hides_zero_rows_but_always_shows_pph21():
    text, _ = _pdf(_slip(pph21_amount=0, ter_rate=0))
    assert "PPh 21 TER A (0%)" in text and "Rp 0" in text        # PPh 21 = 0 is still printed
    for zero in ("Insentif KPI", "Bonus Tambahan", "Kasbon", "Lembur"):
        assert zero not in text, zero


def test_old_snapshot_without_bank_code_falls_back_to_bank_name():
    s = _slip()
    s["employee"].pop("bank_code")
    text, _ = _pdf(s)
    assert "7123456789 (Bank Syariah Indonesia)" in text


def test_alfa_izin_cuts_sit_under_potongan_and_totals_still_add_up():
    s = _slip()
    earn, ded = payslip_lines(s)
    assert not any(k.startswith("Potongan") for k, _ in earn)
    assert ded[:2] == [("Potongan Gaji Pokok (1 hari alfa/izin)", 180000), ("Potongan Tunj. Jabatan (1 hari alfa/izin)", 20000)]
    assert sum(v for _, v in earn[:-1]) == earn[-1][1]          # TOTAL PENDAPATAN = its rows
    assert sum(v for _, v in ded[:-1]) == ded[-1][1]            # TOTAL POTONGAN = its rows
    assert earn[-1][1] - ded[-1][1] == s["take_home_pay"]       # = TOTAL DITERIMA
