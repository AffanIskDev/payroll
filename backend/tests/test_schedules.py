"""Tests for Work Schedules feature (schedules + attendance auto-compute + clock-in/out)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

HRD_CRED = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
BUDI_CRED = {"identifier": "EMP-001", "password": "Password123!"}


def _login(cred):
    r = requests.post(f"{API}/auth/login", json=cred, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def hrd():
    return _login(HRD_CRED)


@pytest.fixture(scope="module")
def budi():
    return _login(BUDI_CRED)


@pytest.fixture(scope="module")
def budi_id(hrd):
    r = requests.get(f"{API}/hr/employees", headers=_h(hrd), timeout=30).json()
    return next(e["id"] for e in r if e["nik"] == "EMP-001")


# ---------- schedules listing & defaults ----------
def test_list_schedules_defaults(hrd):
    r = requests.get(f"{API}/hr/schedules", headers=_h(hrd), timeout=30)
    assert r.status_code == 200
    by_code = {s["code"]: s for s in r.json()}
    assert set(by_code) >= {"KANTOR_PUSAT", "UNIT_2SHIFT", "UNIT_MINGGU"}

    kp = by_code["KANTOR_PUSAT"]
    reg = next(s for s in kp["shifts"] if s["code"] == "REG")
    for i in range(5):
        assert reg["days"][str(i)] == {"start": "08:00", "end": "16:00"}
    assert reg["days"]["5"] == {"start": "08:00", "end": "14:00"}
    assert "6" not in reg["days"]

    u2 = by_code["UNIT_2SHIFT"]
    s1 = next(s for s in u2["shifts"] if s["code"] == "S1")
    s2 = next(s for s in u2["shifts"] if s["code"] == "S2")
    assert s1["days"]["0"] == {"start": "07:00", "end": "15:00"}
    assert s1["days"]["5"] == {"start": "07:00", "end": "13:00"}
    assert s2["days"]["0"] == {"start": "13:00", "end": "21:00"}
    assert s2["days"]["5"] == {"start": "13:00", "end": "19:00"}
    assert "6" not in s1["days"] and "6" not in s2["days"]

    um = by_code["UNIT_MINGGU"]
    s1 = next(s for s in um["shifts"] if s["code"] == "S1")
    s2 = next(s for s in um["shifts"] if s["code"] == "S2")
    for i in range(5):
        assert s1["days"][str(i)] == {"start": "07:00", "end": "15:00"}
        assert s2["days"][str(i)] == {"start": "13:00", "end": "21:00"}
    assert s1["days"]["5"] == {"start": "08:00", "end": "14:00"}
    assert "6" not in s1["days"] or not s1["days"].get("6", {}).get("start")
    assert "5" not in s2["days"] or not s2["days"].get("5", {}).get("start")
    assert s2["days"]["6"] == {"start": "08:00", "end": "14:00"}


def test_update_schedule_invalid_time_rejected(hrd):
    orig = next(s for s in requests.get(f"{API}/hr/schedules", headers=_h(hrd)).json()
                if s["code"] == "KANTOR_PUSAT")
    bad_shifts = [{"code": sh["code"], "name": sh["name"],
                   "days": {**sh["days"], "0": {"start": "16:00", "end": "08:00"}}}
                  for sh in orig["shifts"]]
    r = requests.put(f"{API}/hr/schedules/KANTOR_PUSAT",
                     headers=_h(hrd), json={"name": orig["name"], "shifts": bad_shifts}, timeout=30)
    assert r.status_code == 400


def test_update_schedule_roundtrip(hrd):
    orig = next(s for s in requests.get(f"{API}/hr/schedules", headers=_h(hrd)).json()
                if s["code"] == "KANTOR_PUSAT")
    new_shifts = [{"code": sh["code"], "name": sh["name"],
                   "days": {**sh["days"], "0": {"start": "09:00", "end": "17:00"}}}
                  for sh in orig["shifts"]]
    r = requests.put(f"{API}/hr/schedules/KANTOR_PUSAT",
                     headers=_h(hrd), json={"name": orig["name"], "shifts": new_shifts}, timeout=30)
    assert r.status_code == 200
    updated = r.json()
    reg = next(s for s in updated["shifts"] if s["code"] == "REG")
    assert reg["days"]["0"] == {"start": "09:00", "end": "17:00"}
    # restore
    r = requests.put(f"{API}/hr/schedules/KANTOR_PUSAT",
                     headers=_h(hrd), json={"name": orig["name"], "shifts": orig["shifts"]}, timeout=30)
    assert r.status_code == 200


# ---------- attendance auto-compute (UNIT_2SHIFT) ----------
@pytest.fixture
def budi_as_2shift(hrd, budi_id):
    emp = next(e for e in requests.get(f"{API}/hr/employees", headers=_h(hrd)).json()
               if e["id"] == budi_id)
    payload = {k: emp[k] for k in [
        "nik", "name", "email", "department", "birth_date", "gender", "marital_status",
        "dependents_count", "has_husband_certificate", "payroll_status",
        "prolonged_illness_month_count", "basic_salary", "position_allowance",
        "monthly_attendance_allowance", "overtime_hourly_rate",
        "has_bpjs_kes", "has_bpjs_tk", "jkk_rate", "bank_name", "bank_account_number", "npwp"]}
    payload["work_schedule_code"] = "UNIT_2SHIFT"
    r = requests.put(f"{API}/hr/employees/{budi_id}", headers=_h(hrd), json=payload, timeout=30)
    assert r.status_code == 200
    yield
    payload["work_schedule_code"] = "KANTOR_PUSAT"
    r = requests.put(f"{API}/hr/employees/{budi_id}", headers=_h(hrd), json=payload, timeout=30)
    assert r.status_code == 200


def _post_att(hrd, body):
    r = requests.post(f"{API}/hr/attendance", headers=_h(hrd), json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _del_att(hrd, log_id):
    requests.delete(f"{API}/hr/attendance/{log_id}", headers=_h(hrd), timeout=30)


def test_attendance_2shift_mon_s2(hrd, budi_id, budi_as_2shift):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-06",
                          "check_in_time": "13:10", "check_out_time": "20:45"})
    try:
        assert log["shift_code"] == "S2"
        assert log["minutes_late"] == 10
        assert log["minutes_early_leave"] == 15
        assert log["is_off_day"] is False
    finally:
        _del_att(hrd, log["id"])


def test_attendance_2shift_tue_s1(hrd, budi_id, budi_as_2shift):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-07",
                          "check_in_time": "07:05", "check_out_time": "15:00"})
    try:
        assert log["shift_code"] == "S1"
        assert log["minutes_late"] == 5
        assert log["minutes_early_leave"] == 0
    finally:
        _del_att(hrd, log["id"])


def test_attendance_2shift_sat(hrd, budi_id, budi_as_2shift):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-11",
                          "check_in_time": "13:20", "check_out_time": "18:30"})
    try:
        assert log["shift_code"] == "S2"
        assert log["schedule_start"] == "13:00" and log["schedule_end"] == "19:00"
        assert log["minutes_late"] == 20
        assert log["minutes_early_leave"] == 30
    finally:
        _del_att(hrd, log["id"])


def test_attendance_2shift_sun_off(hrd, budi_id, budi_as_2shift):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-12",
                          "check_in_time": "08:00", "check_out_time": "16:00"})
    try:
        assert log["is_off_day"] is True
        assert log["shift_code"] is None
        assert log["minutes_late"] == 0 and log["minutes_early_leave"] == 0
    finally:
        _del_att(hrd, log["id"])


def test_attendance_2shift_forced_shift(hrd, budi_id, budi_as_2shift):
    # Force S1 even though check_in is 13:00 (closer to S2)
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-06",
                          "check_in_time": "13:00", "check_out_time": "15:00",
                          "shift_code": "S1"})
    try:
        assert log["shift_code"] == "S1"
    finally:
        _del_att(hrd, log["id"])


# ---------- KANTOR_PUSAT ----------
def test_attendance_kp_saturday(hrd, budi_id):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-11",
                          "check_in_time": "08:10", "check_out_time": "13:50"})
    try:
        assert log["shift_code"] == "REG"
        assert log["schedule_start"] == "08:00" and log["schedule_end"] == "14:00"
        assert log["minutes_late"] == 10
        assert log["minutes_early_leave"] == 10
    finally:
        _del_att(hrd, log["id"])


# ---------- UNIT_MINGGU ----------
@pytest.fixture
def budi_as_minggu(hrd, budi_id):
    emp = next(e for e in requests.get(f"{API}/hr/employees", headers=_h(hrd)).json()
               if e["id"] == budi_id)
    payload = {k: emp[k] for k in [
        "nik", "name", "email", "department", "birth_date", "gender", "marital_status",
        "dependents_count", "has_husband_certificate", "payroll_status",
        "prolonged_illness_month_count", "basic_salary", "position_allowance",
        "monthly_attendance_allowance", "overtime_hourly_rate",
        "has_bpjs_kes", "has_bpjs_tk", "jkk_rate", "bank_name", "bank_account_number", "npwp"]}
    payload["work_schedule_code"] = "UNIT_MINGGU"
    requests.put(f"{API}/hr/employees/{budi_id}", headers=_h(hrd), json=payload, timeout=30)
    yield
    payload["work_schedule_code"] = "KANTOR_PUSAT"
    requests.put(f"{API}/hr/employees/{budi_id}", headers=_h(hrd), json=payload, timeout=30)


def test_attendance_minggu_sunday_work(hrd, budi_id, budi_as_minggu):
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-12",
                          "check_in_time": "08:00", "check_out_time": "14:00"})
    try:
        assert log["is_off_day"] is False
        assert log["schedule_start"] == "08:00" and log["schedule_end"] == "14:00"
        assert log["minutes_late"] == 0 and log["minutes_early_leave"] == 0
    finally:
        _del_att(hrd, log["id"])


def test_attendance_minggu_saturday_s1(hrd, budi_id, budi_as_minggu):
    # New UNIT_MINGGU: Saturday S1 08-14 is active; S2 Saturday off.
    log = _post_att(hrd, {"employee_id": budi_id, "work_date": "2026-04-11",
                          "check_in_time": "08:00", "check_out_time": "14:00"})
    try:
        assert log["is_off_day"] is False
        assert log["shift_code"] == "S1"
        assert log["minutes_late"] == 0 and log["minutes_early_leave"] == 0
    finally:
        _del_att(hrd, log["id"])


# ---------- Employee today endpoint ----------
def test_employee_today(budi):
    r = requests.get(f"{API}/v1/employee/attendance/today", headers=_h(budi), timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "day_name" in data and "shifts" in data and "schedule_name" in data


# ---------- Regression: Maret 2026 Budi ----------
def test_regression_maret_budi(hrd):
    periods = requests.get(f"{API}/hr/periods", headers=_h(hrd)).json()
    pid = next(p["id"] for p in periods if p["period_name"] == "Maret 2026")
    r = requests.get(f"{API}/hr/periods/{pid}", headers=_h(hrd), timeout=30)
    assert r.status_code == 200
    data = r.json()
    budi = next(s for s in data["payslips"] if s["employee"]["nik"] == "EMP-001")
    # discipline is projected out; verify thp/pph intact
    assert budi["status"] == "approved"
    # Verify discipline details via workbench
    emp_id = budi["employee_id"]
    wb = requests.get(f"{API}/hr/periods/{pid}/employees/{emp_id}", headers=_h(hrd)).json()
    assert wb["payslip"]["discipline"]["total_points"] == 4
    # 4 points * Rp 40.000 = Rp 160.000 penalty (THP = 7.876.876 - 160.000 = 7.716.876)
    assert wb["payslip"]["take_home_pay"] == 7716876


def test_regression_no_work_time_configs(hrd):
    r = requests.get(f"{API}/hr/configs", headers=_h(hrd), timeout=30)
    assert r.status_code == 200
    keys = {c["config_key"] for c in r.json()}
    assert "WORK_START_TIME" not in keys
    assert "WORK_END_TIME" not in keys
