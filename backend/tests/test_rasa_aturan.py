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
    # user 9 Okt: Poin Absensi = only the days that also cut gaji pokok (alfa/izin); sakit/cuti count as Poin Presensi
    logs = [_day("hadir", minutes_late=75), _day("cuti", work_date="2026-10-02"),
            _day("izin", work_date="2026-10-03")]
    disc = calc_discipline(logs)
    assert disc["total_points"] == 1                     # lateness: late >= 60 min
    assert disc["presence_points"] == 2                  # Poin Presensi: lateness 1 + cuti 1
    assert disc["presence_by_type"] == {"annual_leave": 1}
    assert disc["absence_points"] == 1                   # Poin Absensi: izin
    assert disc["absence_by_type"] == {"permission_leave": 1}
    slip = compute_payslip(EMP, logs, CFG, {})
    assert (slip["late_penalty_points"], slip["absence_points"]) == (2, 1)
    assert slip["late_penalty_amount"] == 3 * 30000     # (2 + 1) / 25 of the attendance allowance — unchanged total


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


def test_bonus_and_target_deduction_come_from_rosy_like_transport():
    # user 10 Okt: Bonus & Potongan Tidak Mencapai Target diambil dari Tambahan Bulanan ROSY, seperti Transport Homecare
    row = {"komponen_bulanan": [
        {"component_id": "KOMP-00022", "nama": "Transport Rumat Kita", "tipe": "pendapatan", "nominal": 1350000.0},
        {"component_id": "KOMP-00005", "nama": "Bonus", "tipe": "pendapatan", "nominal": 3184400.0},
        {"component_id": "KOMP-00015", "nama": "Potongan Tidak Mencapai Target", "tipe": "potongan", "nominal": 500000.0},
        {"component_id": "KOMP-00023", "nama": "Lembur", "tipe": "pendapatan", "nominal": 90000.0}]}
    assert integrations.monthly_components(row) == {"TRANSPORT_HOMECARE": 1350000.0, "BONUS": 3184400.0,
                                                    "TARGET_DEDUCTION": 500000.0}
    assert integrations.monthly_components({"komponen_bulanan": [{"component_id": "KOMP-00005", "nominal": 0}]}) == {}


def test_target_deduction_cuts_take_home_pay_but_not_the_pph21_base():
    base = compute_payslip(EMP, [], CFG, {})
    slip = compute_payslip(EMP, [], CFG, {"target_deduction": 500000})
    assert slip["target_deduction"] == 500000
    # as in ROSY (brutoPajak counts only pendapatan): a potongan component never lowers the PPh 21 base
    assert (slip["gross_earnings"], slip["taxable_gross"], slip["pph21_amount"]) == \
        (base["gross_earnings"], base["taxable_gross"], base["pph21_amount"])
    assert slip["total_deductions"] - base["total_deductions"] == 500000
    assert base["take_home_pay"] - slip["take_home_pay"] == 500000
    unpaid = compute_payslip({**EMP, "payroll_status": "unpaid_leave"}, [], CFG, {"target_deduction": 500000})
    assert unpaid["target_deduction"] == 0


# ---------------------------------------------------------------- PJUnit: target cut off the Bonus Threshold (13 Oct)
PJUNIT = {**EMP, "department": "Pelayanan", "position": "Penanggung Jawab unit"}


@pytest.mark.parametrize("emp,expected", [
    ({"department": "Pelayanan", "position": "Penanggung Jawab unit"}, True),      # the position's name in ROSY
    ({"department": " pelayanan ", "position": "PENANGGUNG  JAWAB UNIT"}, True),
    ({"department": "Pelayanan", "position": "PJ Unit"}, True), ({"department": "Pelayanan", "position": "PJUnit"}, True),
    ({"department": "Pelayanan", "position": "Perawat"}, False),
    ({"department": "Pelayanan", "position": "Supervisor Pelayanan"}, False),
    ({"department": "Marketing", "position": "Penanggung Jawab unit"}, False),     # PJUnit is a Pelayanan position
    ({}, False), (None, False),
])
def test_pjunit_is_the_penanggung_jawab_unit_in_pelayanan(emp, expected):
    from labels import is_pjunit
    assert is_pjunit(emp) is expected


def test_pjunit_target_deduction_comes_off_the_bonus_threshold():
    # user 13 Okt: PJUnit yang tidak mencapai target tidak jadi menerima Bonus Threshold-nya — bukan pendapatan, dan
    # tidak ditaruh lagi di potongan supaya tidak dobel
    base = compute_payslip(PJUNIT, [], CFG, {})
    slip = compute_payslip(PJUNIT, [], CFG, {"target_deduction": 500000})
    assert (slip["position_allowance"], slip["target_from_bonus"], slip["target_deduction"]) == (0, 500000, 0)
    assert base["gross_earnings"] - slip["gross_earnings"] == 500000
    assert base["taxable_gross"] - slip["taxable_gross"] == 500000          # a bonus not earned is not taxed
    tax_saved = base["pph21_amount"] - slip["pph21_amount"]
    assert tax_saved > 0
    assert base["take_home_pay"] - slip["take_home_pay"] == 500000 - tax_saved
    assert base["total_deductions"] - slip["total_deductions"] == tax_saved   # no potongan row added
    # not a PJUnit (a Perawat, also in Pelayanan): still a potongan after tax, as in ROSY
    perawat = compute_payslip({**PJUNIT, "position": "Perawat"}, [], CFG, {"target_deduction": 500000})
    assert (perawat["position_allowance"], perawat["target_from_bonus"], perawat["target_deduction"]) == \
        (500000, 0, 500000)
    assert perawat["taxable_gross"] == base["taxable_gross"]


@pytest.mark.parametrize("allowance,expected", [
    (1000000, (500000, 500000, 0)),     # bonus left over
    (300000, (0, 300000, 200000)),      # only the Bonus Threshold there is; the rest stays a potongan
    (0, (0, 0, 500000)),                # ROSY Sep 2026 has PJUnit with Bonus Threshold 0: never a negative income
])
def test_pjunit_target_comes_off_only_as_far_as_the_bonus_threshold_goes(allowance, expected):
    slip = compute_payslip({**PJUNIT, "position_allowance": allowance}, [], CFG, {"target_deduction": 500000})
    assert (slip["position_allowance"], slip["target_from_bonus"], slip["target_deduction"]) == expected


def test_pjunit_bonus_threshold_lost_to_the_target_is_not_cut_again_for_alfa():
    slip = compute_payslip(PJUNIT, [_day("alfa")], CFG, {"target_deduction": 500000})
    assert slip["position_deduction_amount"] == 0                  # nothing left of the Bonus Threshold to cut
    assert (slip["absent_deduction_amount"], slip["absence_penalty_amount"]) == (180000, 30000)  # gapok & kehadiran
    left = compute_payslip({**PJUNIT, "position_allowance": 1000000}, [_day("alfa")], CFG, {"target_deduction": 500000})
    assert left["position_deduction_amount"] == 20000              # 1/25 of the 500 rb that is left


def test_thr_and_installment_come_from_rosy_like_bonus():
    # user 12 Okt: THR & Cicilan / Pinjaman diambil dari Tambahan Bulanan ROSY, seperti Bonus
    row = {"komponen_bulanan": [
        {"component_id": "KOMP-00014", "nama": "THR", "tipe": "pendapatan", "nominal": 4500000.0},
        {"component_id": "KOMP-00007", "nama": "Cicilan / Pinjaman", "tipe": "potongan", "nominal": 350000.0},
        {"component_id": "KOMP-00005", "nama": "Bonus", "tipe": "pendapatan", "nominal": 50000.0},
        {"component_id": "KOMP-00006", "nama": "PPh 21", "tipe": "potongan", "nominal": 12345.0}]}  # RASA's own
    assert integrations.monthly_components(row) == {"THR": 4500000.0, "LOAN_INSTALLMENT": 350000.0, "BONUS": 50000.0}


def test_thr_is_taxable_income_but_not_bpjs_wage():
    base = compute_payslip(EMP, [], CFG, {})
    slip = compute_payslip(EMP, [], CFG, {"thr": 4500000})
    assert slip["thr"] == 4500000
    assert slip["gross_earnings"] - base["gross_earnings"] == 4500000
    assert slip["taxable_gross"] - base["taxable_gross"] == 4500000          # brutoPajak, like Bonus
    assert slip["bpjs"] == base["bpjs"]                                       # never part of the BPJS wage
    assert slip["pph21_amount"] > base["pph21_amount"]
    unpaid = compute_payslip({**EMP, "payroll_status": "unpaid_leave"}, [], CFG, {"thr": 4500000})
    assert unpaid["thr"] == 0


def test_installment_cuts_take_home_pay_but_not_the_pph21_base():
    base = compute_payslip(EMP, [], CFG, {})
    slip = compute_payslip(EMP, [], CFG, {"loan_installment": 350000})
    assert slip["loan_installment"] == 350000
    assert (slip["gross_earnings"], slip["taxable_gross"], slip["pph21_amount"]) == \
        (base["gross_earnings"], base["taxable_gross"], base["pph21_amount"])
    assert slip["total_deductions"] - base["total_deductions"] == 350000
    assert base["take_home_pay"] - slip["take_home_pay"] == 350000
    unpaid = compute_payslip({**EMP, "payroll_status": "unpaid_leave"}, [], CFG, {"loan_installment": 350000})
    assert unpaid["loan_installment"] == 0


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
                  "TOTAL DITERIMA", "Transport Homecare", "Potongan Absensi", "1 hari izin"):
        assert label in text, label
    flat = " ".join(text.split())                                 # the disclaimer wraps over lines
    assert "Catatan: Slip gaji ini dibuat berdasarkan data yang tersedia" in flat
    assert "perusahaan berhak melakukan koreksi dan penyesuaian sesuai ketentuan yang berlaku." in flat
    assert "menghubungi Divisi HRD" not in flat
    assert "PENDAPATAN" in text and "TOTAL PENDAPATAN" in text
    for gone in ("Status PTKP Efektif", "TAKE HOME PAY", "Kompensasi", "[NAMA_PERUSAHAAN]", "[NAMA_PENANDATANGAN]",
                 "PENERIMAAN", "Potongan Gaji Pokok", "Potongan Tunj. Jabatan", "Potongan Presensi"):
        assert gone not in text, gone


def test_payslip_signer_comes_from_rosy():
    text, _ = _pdf(_slip())
    assert "Meliawasni" in text and "Manager HRD" in text


def test_payslip_hides_zero_rows_but_always_shows_pph21():
    text, _ = _pdf(_slip(pph21_amount=0, ter_rate=0))
    assert "PPh 21 TER A (0%)" in text and "Rp 0" in text        # PPh 21 = 0 is still printed
    for zero in ("Insentif KPI", "Bonus", "Kasbon", "Lembur"):
        assert zero not in text, zero


def test_payslip_bonus_label():
    earn, _ = payslip_lines(_slip(additional_bonus=500000))
    assert ("Bonus", 500000, "") in earn and not any(r[0] == "Bonus Tambahan" for r in earn)


def test_payslip_prints_target_deduction_only_when_set():
    _, ded = payslip_lines(_slip(target_deduction=500000))
    assert ("Potongan Tidak Mencapai Target", 500000, "") in ded
    _, ded = payslip_lines(_slip())
    assert not any(r[0] == "Potongan Tidak Mencapai Target" for r in ded)


def _pjunit_slip(allowance=500000):
    s = compute_payslip({**PJUNIT, "position_allowance": allowance}, [], CFG, {"target_deduction": 500000})
    s["employee"] = {**_slip()["employee"], "department": "Pelayanan"}
    s["position_allowance_label"] = "Bonus Threshold"
    return s


def test_payslip_shows_the_pjunit_bonus_threshold_after_the_target_cut():
    s = _pjunit_slip()
    earn, ded = payslip_lines(s)
    # printed even at Rp 0, so the employee sees where the Bonus Threshold went; no potongan row on top of it
    assert ("Bonus Threshold", 0, "Rp 500.000, dipotong Rp 500.000 karena tidak mencapai target") in earn
    assert not any(r[0] == "Potongan Tidak Mencapai Target" for r in ded)
    amount = lambda rows, k: next(v for n, v, _ in rows if n == k)  # noqa: E731
    assert amount(earn, "TOTAL PENDAPATAN") - amount(ded, "TOTAL POTONGAN") == s["take_home_pay"]
    flat = " ".join(_pdf(s)[0].split())
    assert "Bonus Threshold" in flat and "dipotong Rp 500.000" in flat and "Potongan Tidak Mencapai Target" not in flat
    # Bonus Threshold smaller than the potongan: it is used up and only the rest is printed as a potongan
    earn, ded = payslip_lines(_pjunit_slip(300000))
    assert ("Bonus Threshold", 0, "Rp 300.000, dipotong Rp 300.000 karena tidak mencapai target") in earn
    assert ("Potongan Tidak Mencapai Target", 200000, "") in ded


def test_payslip_prints_thr_and_installment_only_when_set():
    earn, ded = payslip_lines(_slip(thr=4500000, loan_installment=350000, other_deductions=100000))
    assert ("THR", 4500000, "") in earn and ("Cicilan / Pinjaman", 350000, "") in ded
    # THR right after Bonus's place; Cicilan with the other money cuts: after PPh 21, before Kasbon
    assert [r[0] for r in earn].index("THR") == [r[0] for r in earn].index("Transport Homecare") + 1
    assert [r[0] for r in ded][-4:] == [ded[-4][0], "Cicilan / Pinjaman", "Kasbon / Potongan Lain", "TOTAL POTONGAN"]
    assert ded[-4][0].startswith("PPh 21")
    earn, ded = payslip_lines(_slip())                                       # slips without them: no rows
    assert not any(r[0] == "THR" for r in earn) and not any(r[0] == "Cicilan / Pinjaman" for r in ded)
    text, _ = _pdf(_slip(thr=4500000, loan_installment=350000))
    assert "THR" in text and "Cicilan / Pinjaman" in text


@pytest.mark.parametrize("dept,label", [("Pelayanan", "Bonus Threshold"), (" pelayanan ", "Bonus Threshold"),
                                        ("Perawat", "Tunjangan Jabatan"), ("Human Capital", "Tunjangan Jabatan"),
                                        (None, "Tunjangan Jabatan")])
def test_pelayanan_reads_bonus_threshold_for_the_position_allowance(dept, label):
    from labels import position_allowance_label
    assert position_allowance_label({"department": dept}) == label
    s = _slip()
    s["employee"]["department"] = dept
    earn, _ = payslip_lines(s)
    assert (label, s["position_allowance"], "") in earn


def test_bonus_threshold_on_the_printed_slip():
    s = _slip(position_allowance_label="Bonus Threshold")                  # label stored by build_slip
    text, _ = _pdf(s)
    assert "Bonus Threshold" in text and "Tunjangan Jabatan" not in text
    text, _ = _pdf(_slip())                                                  # Perawat: unchanged
    assert "Tunjangan Jabatan" in text and "Bonus Threshold" not in text


def test_old_snapshot_without_bank_code_falls_back_to_bank_name():
    s = _slip()
    s["employee"].pop("bank_code")
    text, _ = _pdf(s)
    assert "7123456789 (Bank Syariah Indonesia)" in text


def test_presensi_and_absensi_split_adds_up_to_the_attendance_cut():
    logs = [_day("hadir", minutes_late=75), _day("cuti", work_date="2026-10-02"), _day("sakit", work_date="2026-10-03")]
    slip = compute_payslip(EMP, logs, CFG, {})
    # lateness + cuti + sakit are all Poin Presensi now; no alfa/izin → nothing under Potongan Absensi
    assert slip["presence_penalty_amount"] == 90000 and slip["absence_penalty_amount"] == 0
    assert slip["presence_penalty_amount"] + slip["absence_penalty_amount"] == slip["late_penalty_amount"]
    mixed = compute_payslip(EMP, [_day("hadir", minutes_late=75), _day("sakit", work_date="2026-10-02"),
                                  _day("alfa", work_date="2026-10-03")], CFG, {})
    assert mixed["presence_penalty_amount"] == 60000 and mixed["absence_penalty_amount"] == 30000
    capped = compute_payslip(EMP, [_day("hadir", minutes_late=75)] + [_day("alfa", work_date=f"2026-10-{d:02d}")
                                                                       for d in range(2, 31)], CFG, {})
    assert capped["absence_penalty_amount"] == 750000 and capped["presence_penalty_amount"] == 0


def test_slip_shows_only_cuts_that_have_a_value():
    earn, ded = payslip_lines(_slip())                           # 1 izin day, no lateness
    labels = [k for k, _, _ in ded]
    # izin (PPT): attendance 30.000 + gaji pokok 180.000 + jabatan 20.000, all under one Potongan Absensi line
    assert ("Potongan Absensi", 230000, "1 hari izin") in ded
    assert not any(k.startswith(("Potongan Presensi", "Potongan Gaji Pokok", "Potongan Tunj")) for k in labels)
    assert ("Tunjangan Kehadiran", 750000, "") in earn           # in full; the cut sits under POTONGAN
    logs = [_day("hadir", minutes_late=75), _day("alfa", work_date="2026-10-02"), _day("alfa", work_date="2026-10-03"),
            _day("cuti", work_date="2026-10-04")]
    s = {**compute_payslip(EMP, logs, CFG, {}), "employee": _slip()["employee"]}
    _, ded = payslip_lines(s)
    # cuti only cuts the attendance allowance → Potongan Presensi; alfa also cuts gapok & jabatan → Potongan Absensi
    assert ("Potongan Presensi", 60000, "1x telat/pulang cepat min. 60 mnt, 1 hari cuti tahunan") in ded
    assert ("Potongan Absensi", 60000 + 360000 + 40000, "2 hari alfa") in ded


def test_all_cuts_sit_under_potongan_and_totals_still_add_up():
    s = _slip()
    earn, ded = payslip_lines(s)
    assert not any(k.startswith("Potongan") for k, _, _ in earn)
    assert sum(v for _, v, _ in earn[:-1]) == earn[-1][1]       # TOTAL PENDAPATAN = its rows
    assert sum(v for _, v, _ in ded[:-1]) == ded[-1][1]         # TOTAL POTONGAN = its rows
    assert earn[-1][1] - ded[-1][1] == s["take_home_pay"]       # = TOTAL DITERIMA
