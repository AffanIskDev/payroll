"""Iteration 9 — ROSY/RUMATKU integration simplification.

Covers:
- GET /api/hr/integrations returns {rosy:{mode:'mock'}, rumatku:{mode:'mock'}}
- POST /api/hr/periods auto-syncs employees from ROSY (employee_count=3, employees_synced_at)
- POST /api/hr/periods/{pid}/fetch-attendance fetches logs from RUMATKU mock,
  replaces logs in range, auto-calculates payslips.
  * April 2026 TEST period → 90 logs (3 emp × 30 days)
  * Budi overtime from logs → payslip.overtime_pay > 0 at Rp 50.000/jam
  * March 2026 range returns BUDI_MARCH dataset (4 poin / Rp 160.000)
- fetch-attendance on approved 'Maret 2026' → 400 (locked)
- Removed endpoints return 404/405: POST/PUT /hr/employees,
  POST/DELETE /hr/attendance, /hr/attendance/import, /hr/schedules,
  /hr/shift-rotations, /v1/employee/attendance/*
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
STAFF = {"identifier": "staff.hr@rumatku.id", "password": "Password123!"}
BUDI = {"identifier": "EMP-001", "password": "Password123!"}


def _login(c):
    r = requests.post(f"{API}/auth/login", json=c, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def hrd_tok():
    return _login(HRD)


@pytest.fixture(scope="module")
def staff_tok():
    return _login(STAFF)


@pytest.fixture(scope="module")
def budi_tok():
    return _login(BUDI)


@pytest.fixture(scope="module")
def emp_map(hrd_tok):
    r = requests.get(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30)
    assert r.status_code == 200
    return {e["nik"]: e for e in r.json()}


# ---------- Integrations status ----------
class TestIntegrations:
    def test_integrations_endpoint(self, hrd_tok):
        r = requests.get(f"{API}/hr/integrations", headers=_h(hrd_tok), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rosy"]["mode"] == "mock"
        assert d["rumatku"]["mode"] == "mock"

    def test_integrations_requires_hr(self, budi_tok):
        r = requests.get(f"{API}/hr/integrations", headers=_h(budi_tok), timeout=30)
        assert r.status_code == 403


# ---------- Create period auto-syncs employees from ROSY ----------
class TestCreatePeriodSyncsEmployees:
    def test_create_period_fetches_employees(self, hrd_tok):
        pname = "TEST_Iter9 Apr Sync"
        # Clean stale
        for p in requests.get(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=30).json():
            if p["period_name"] == pname:
                requests.delete(f"{API}/hr/periods/{p['id']}", headers=_h(hrd_tok), timeout=30)
        r = requests.post(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=60,
                          json={"period_name": pname, "start_date": "2026-04-01",
                                "end_date": "2026-04-30", "payment_date": "2026-05-05"})
        assert r.status_code == 200, r.text
        d = r.json()
        try:
            assert d["employee_count"] == 3, d
            assert len(d["employee_ids"]) == 3
            assert d["employees_synced_at"]
            assert d["employees_source"] == "mock"
            assert d["attendance_synced_at"] is None
            assert d["status"] == "draft"
        finally:
            requests.delete(f"{API}/hr/periods/{d['id']}", headers=_h(hrd_tok), timeout=30)


# ---------- Fetch attendance ----------
class TestFetchAttendance:
    @pytest.fixture(scope="class")
    def april_period(self, hrd_tok):
        pname = "TEST_Iter9 Apr Fetch"
        for p in requests.get(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=30).json():
            if p["period_name"] == pname:
                requests.delete(f"{API}/hr/periods/{p['id']}", headers=_h(hrd_tok), timeout=30)
        r = requests.post(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=60,
                          json={"period_name": pname, "start_date": "2026-04-01",
                                "end_date": "2026-04-30", "payment_date": "2026-05-05"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        yield pid
        requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok), timeout=30)

    def test_fetch_attendance_apr_mock(self, hrd_tok, april_period):
        r = requests.post(f"{API}/hr/periods/{april_period}/fetch-attendance",
                          headers=_h(hrd_tok), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        # 3 emp × 30 days = 90 logs
        assert d["logs"] == 90, d
        assert d["processed"] == 3
        assert d["unknown_niks"] == []

    def test_fetch_attendance_populates_period(self, hrd_tok, april_period):
        p = requests.get(f"{API}/hr/periods/{april_period}",
                         headers=_h(hrd_tok), timeout=30).json()["period"]
        assert p["attendance_synced_at"]
        assert p["attendance_count"] == 90
        assert p["attendance_source"] == "mock"

    def test_fetch_attendance_budi_overtime_from_logs(self, hrd_tok, april_period, emp_map):
        eid = emp_map["EMP-001"]["id"]
        wb = requests.get(f"{API}/hr/periods/{april_period}/employees/{eid}",
                          headers=_h(hrd_tok), timeout=30).json()
        slip = wb["payslip"]
        ot_hours_from_logs = sum(l.get("overtime_hours") or 0 for l in wb["attendance"])
        # overtime_pay = ot_hours × 50000 (Budi rate)
        assert slip["overtime_pay"] == ot_hours_from_logs * 50000, (slip["overtime_pay"], ot_hours_from_logs)
        # overtime_hours in slip should reflect logs (read-only)
        assert slip["overtime_hours"] == ot_hours_from_logs

    def test_fetch_attendance_rejected_on_approved_period(self, hrd_tok):
        periods = requests.get(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=30).json()
        maret = next((p for p in periods if p["period_name"] == "Maret 2026"), None)
        if not maret or maret["status"] != "approved":
            pytest.skip("Maret 2026 approved period not present")
        r = requests.post(f"{API}/hr/periods/{maret['id']}/fetch-attendance",
                          headers=_h(hrd_tok), timeout=30)
        assert r.status_code == 400, r.text

    def test_fetch_attendance_march_range_budi_dataset(self, hrd_tok, emp_map):
        """March 2026 range in RUMATKU mock returns BUDI_MARCH dataset only.
        Verify by creating a TEST period for a different month, then force-fetching with
        a March-start date would require backend change. Instead: use mock _mock_rumatku
        directly by calling fetch_attendance via a test March period."""
        pname = "TEST_Iter9 Mar Fetch"
        for p in requests.get(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=30).json():
            if p["period_name"] == pname:
                requests.delete(f"{API}/hr/periods/{p['id']}", headers=_h(hrd_tok), timeout=30)
        r = requests.post(f"{API}/hr/periods", headers=_h(hrd_tok), timeout=60,
                          json={"period_name": pname, "start_date": "2026-03-01",
                                "end_date": "2026-03-31", "payment_date": "2026-04-05"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        try:
            f = requests.post(f"{API}/hr/periods/{pid}/fetch-attendance",
                              headers=_h(hrd_tok), timeout=120)
            assert f.status_code == 200, f.text
            d = f.json()
            # BUDI_MARCH has 18 entries, all for EMP-001
            assert d["logs"] == 18, d
            # Siti/Dimas unknown in this range → nothing for them; those NIKs not in response → unknown_niks empty
            # Verify Budi slip has 4 poin / Rp 160.000
            eid = emp_map["EMP-001"]["id"]
            wb = requests.get(f"{API}/hr/periods/{pid}/employees/{eid}",
                              headers=_h(hrd_tok), timeout=30).json()
            slip = wb["payslip"]
            assert slip.get("late_penalty_points") == 4, slip.get("late_penalty_points")
            assert slip.get("late_penalty_amount") == 160000, slip.get("late_penalty_amount")
        finally:
            requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok), timeout=30)

    def test_fetch_attendance_requires_hr(self, budi_tok, april_period):
        r = requests.post(f"{API}/hr/periods/{april_period}/fetch-attendance",
                          headers=_h(budi_tok), timeout=30)
        assert r.status_code == 403


# ---------- Removed endpoints ----------
class TestRemovedEndpoints:
    def test_post_employee_removed(self, hrd_tok):
        r = requests.post(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30,
                          json={"nik": "TEST_X", "name": "x"})
        assert r.status_code in (404, 405), r.status_code

    def test_put_employee_removed(self, hrd_tok, emp_map):
        eid = emp_map["EMP-001"]["id"]
        r = requests.put(f"{API}/hr/employees/{eid}", headers=_h(hrd_tok), timeout=30, json={})
        assert r.status_code in (404, 405), r.status_code

    def test_delete_employee_removed(self, hrd_tok, emp_map):
        eid = emp_map["EMP-001"]["id"]
        r = requests.delete(f"{API}/hr/employees/{eid}", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_post_attendance_removed(self, hrd_tok):
        r = requests.post(f"{API}/hr/attendance", headers=_h(hrd_tok), timeout=30, json={})
        assert r.status_code in (404, 405), r.status_code

    def test_delete_attendance_removed(self, hrd_tok):
        r = requests.delete(f"{API}/hr/attendance/x", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_attendance_import_removed(self, hrd_tok):
        r = requests.post(f"{API}/hr/attendance/import", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_attendance_import_template_removed(self, hrd_tok):
        r = requests.get(f"{API}/hr/attendance/import-template", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_schedules_removed(self, hrd_tok):
        r = requests.get(f"{API}/hr/schedules", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_rotations_removed(self, hrd_tok):
        r = requests.get(f"{API}/hr/shift-rotations", headers=_h(hrd_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code

    def test_employee_clock_in_removed(self, budi_tok):
        r = requests.post(f"{API}/v1/employee/attendance/clock-in",
                          headers=_h(budi_tok), timeout=30, json={})
        assert r.status_code in (404, 405), r.status_code

    def test_employee_attendance_today_removed(self, budi_tok):
        r = requests.get(f"{API}/v1/employee/attendance/today",
                         headers=_h(budi_tok), timeout=30)
        assert r.status_code in (404, 405), r.status_code


# ---------- Recap shift uses logs ----------
class TestShiftRecapFromLogs:
    def test_shift_recap_maret_from_logs(self, hrd_tok):
        r = requests.get(f"{API}/hr/shift-recap", headers=_h(hrd_tok),
                         params={"month": "2026-03"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["month"] == "2026-03"
        assert d["days_in_month"] == 31
        assert isinstance(d["shift_codes"], list)
        assert isinstance(d["rows"], list) and len(d["rows"]) >= 1
        for row in d["rows"]:
            for k in ("nik", "name", "shifts", "off_days", "leave",
                      "present_no_shift", "total_worked", "no_log"):
                assert k in row, (k, row)
        # Budi should have REG count from BUDI_MARCH (all 18 are present REG shift)
        budi = next((r_ for r_ in d["rows"] if r_["nik"] == "EMP-001"), None)
        assert budi is not None
        assert budi["shifts"].get("REG", 0) >= 1
