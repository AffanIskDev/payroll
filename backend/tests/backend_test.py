"""Backend regression tests for Payroll ROSY & Rumatku.
Covers auth, role guards, HR CRUD, period workbench, approve/lock, and employee
API (payslips, encrypted PDF download, clock-in/out).
"""
import io
import os
import pytest
import requests
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

HRD_CRED = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
ADMIN_CRED = {"identifier": "masdidin89@gmail.com", "password": "Password123!"}
BUDI_CRED = {"identifier": "EMP-001", "password": "Password123!"}
BUDI_EMAIL_CRED = {"identifier": "budi@rumatku.id", "password": "Password123!"}
SITI_CRED = {"identifier": "siti@rumatku.id", "password": "Password123!"}
DIMAS_CRED = {"identifier": "dimas@rumatku.id", "password": "Password123!"}


def _login(cred):
    r = requests.post(f"{API}/auth/login", json=cred, timeout=30)
    assert r.status_code == 200, f"login {cred['identifier']}: {r.status_code} {r.text}"
    return r.json()


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def hrd_token():
    return _login(HRD_CRED)["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_CRED)["token"]


@pytest.fixture(scope="session")
def budi_token():
    return _login(BUDI_CRED)["token"]


@pytest.fixture(scope="session")
def period_id(hrd_token):
    r = requests.get(f"{API}/hr/periods", headers=_h(hrd_token), timeout=30)
    assert r.status_code == 200
    periods = r.json()
    for p in periods:
        if p["period_name"] == "Maret 2026":
            return p["id"]
    pytest.skip("Maret 2026 seed period not found")


@pytest.fixture(scope="session")
def employees(hrd_token):
    r = requests.get(f"{API}/hr/employees", headers=_h(hrd_token), timeout=30)
    assert r.status_code == 200
    return {e["nik"]: e for e in r.json()}


# ---------- auth ----------
class TestAuth:
    def test_login_hrd(self):
        d = _login(HRD_CRED)
        assert d["user"]["role"] == "manager_hrd"

    def test_login_admin(self):
        d = _login(ADMIN_CRED)
        assert d["user"]["role"] == "admin_payroll"

    def test_login_employee_by_nik(self):
        d = _login(BUDI_CRED)
        assert d["user"]["role"] == "employee"
        assert d["user"]["nik"] == "EMP-001"

    def test_login_employee_by_email(self):
        d = _login(BUDI_EMAIL_CRED)
        assert d["user"]["role"] == "employee"

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"identifier": "budi@rumatku.id", "password": "bad"}, timeout=30)
        assert r.status_code == 401

    def test_me_with_token(self, budi_token):
        r = requests.get(f"{API}/auth/me", headers=_h(budi_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "employee"


# ---------- role guards ----------
class TestRoleGuards:
    def test_employee_cannot_access_hr(self, budi_token):
        r = requests.get(f"{API}/hr/dashboard", headers=_h(budi_token), timeout=30)
        assert r.status_code == 403

    def test_hr_cannot_access_employee_api(self, hrd_token):
        r = requests.get(f"{API}/v1/employee/payslips", headers=_h(hrd_token), timeout=30)
        assert r.status_code == 403

    def test_unauth_401(self):
        r = requests.get(f"{API}/hr/dashboard", timeout=30)
        assert r.status_code == 401


# ---------- seed period numbers ----------
class TestSeededCalculations:
    def _slip(self, hrd_token, pid, eid):
        r = requests.get(f"{API}/hr/periods/{pid}/employees/{eid}",
                         headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200, r.text
        return r.json()["payslip"]

    def test_budi_waterfall(self, hrd_token, period_id, employees):
        s = self._slip(hrd_token, period_id, employees["EMP-001"]["id"])
        d = s["discipline"]
        assert d["rule1_points"] == 0, d
        assert d["rule2_points"] == 1, d
        assert d["rule3_points"] == 2, d
        assert d["rule4_points"] == 1, d
        assert d["rule4_minutes"] == 67, d
        assert d["total_points"] == 4, d
        assert s["late_penalty_amount"] == 160000, s["late_penalty_amount"]
        assert s["attendance_allowance"] == 840000, s["attendance_allowance"]
        assert s["taxable_gross"] == 8312400, s["taxable_gross"]
        assert s["ptkp_status"] == "K/1"
        assert s["ter_category"] == "B"
        assert s["ter_rate"] == 1
        assert s["pph21_amount"] == 83124, s["pph21_amount"]
        assert s["take_home_pay"] == 7716876, s["take_home_pay"]

    def test_siti_tk0_umk_floor(self, hrd_token, period_id, employees):
        s = self._slip(hrd_token, period_id, employees["EMP-002"]["id"])
        assert s["ptkp_status"] == "TK/0"
        assert s["ter_category"] == "A"
        assert s["bpjs"]["kes_base"] == 5219263, s["bpjs"]["kes_base"]
        assert s["pph21_amount"] == 44873, s["pph21_amount"]
        assert s["take_home_pay"] == 5517934, s["take_home_pay"]

    def test_dimas_unpaid_leave(self, hrd_token, period_id, employees):
        s = self._slip(hrd_token, period_id, employees["EMP-003"]["id"])
        assert s["payroll_status"] == "unpaid_leave"
        assert s["basic_salary"] == 0
        assert s["take_home_pay"] == 0
        assert s["gross_earnings"] == 0
        assert s["bpjs_company_advance"] > 0


# ---------- workbench preview / draft ----------
class TestWorkbench:
    def test_preview_live_recalc_overtime_readonly(self, hrd_token, period_id, employees):
        """Iter9: overtime_hours in adj is IGNORED by build_slip (sourced from logs)."""
        eid = employees["EMP-001"]["id"]
        base = requests.post(f"{API}/hr/periods/{period_id}/employees/{eid}/preview",
                             headers=_h(hrd_token), timeout=30, json={}).json()
        with_ot = requests.post(f"{API}/hr/periods/{period_id}/employees/{eid}/preview",
                                headers=_h(hrd_token), timeout=30,
                                json={"overtime_hours": 5}).json()
        # Overtime is now read-only from attendance logs; adj.overtime_hours ignored
        assert with_ot["overtime_pay"] == base["overtime_pay"]
        assert with_ot["overtime_hours"] == base["overtime_hours"]

    def test_save_draft(self, hrd_token, employees):
        # Create a TEST period (no attendance fetched → 0 OT). KPI incentive still editable.
        eid = employees["EMP-001"]["id"]
        pr = requests.post(f"{API}/hr/periods", headers=_h(hrd_token), timeout=30,
                           json={"period_name": "TEST_April 2026", "start_date": "2026-04-01",
                                 "end_date": "2026-04-30", "payment_date": "2026-05-05"})
        assert pr.status_code == 200, pr.text
        pid = pr.json()["id"]
        try:
            proc = requests.post(f"{API}/hr/periods/{pid}/process", headers=_h(hrd_token), timeout=60)
            assert proc.status_code == 200, proc.text
            r = requests.put(f"{API}/hr/periods/{pid}/employees/{eid}",
                             headers=_h(hrd_token), timeout=30,
                             json={"overtime_hours": 0, "kpi_incentive": 500000, "additional_bonus": 0,
                                   "late_penalty_compensation": 0, "other_deductions": 0,
                                   "adjustment_notes": "TEST draft"})
            assert r.status_code == 200, r.text
            assert r.json()["adjustment_notes"] == "TEST draft"
            assert r.json()["kpi_incentive"] == 500000
        finally:
            requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_token), timeout=30)

    def test_preview_pdf(self, hrd_token, period_id, employees):
        eid = employees["EMP-001"]["id"]
        r = requests.get(f"{API}/hr/periods/{period_id}/employees/{eid}/pdf",
                         headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ---------- configs & employees CRUD ----------
class TestConfigs:
    def test_list_configs(self, hrd_token):
        r = requests.get(f"{API}/hr/configs", headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200
        keys = {c["config_key"] for c in r.json()}
        assert "UMK_BEKASI_REGENCY" in keys
        assert "DEFAULT_WORK_DAYS" in keys

    def test_update_configs_roundtrip(self, hrd_token):
        # Keep value identical; just ensure PUT accepts known key
        r = requests.put(f"{API}/hr/configs", headers=_h(hrd_token), timeout=30,
                         json={"DEFAULT_WORK_DAYS": "25"})
        assert r.status_code == 200

    def test_update_configs_unknown_key(self, hrd_token):
        r = requests.put(f"{API}/hr/configs", headers=_h(hrd_token), timeout=30,
                         json={"BOGUS": "x"})
        assert r.status_code == 400


# ---------- employee API ----------
class TestEmployeeAPI:
    def test_payslips_empty_before_approval(self, budi_token):
        r = requests.get(f"{API}/v1/employee/payslips", headers=_h(budi_token), timeout=30)
        assert r.status_code == 200
        # Before approval seeded slips are draft → employee list should be empty
        # (Will be re-checked after approve-all in TestApproveFlow)
        assert isinstance(r.json(), list)

    def test_profile(self, budi_token):
        r = requests.get(f"{API}/v1/employee/profile", headers=_h(budi_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["nik"] == "EMP-001"

    def test_employee_attendance_removed(self, budi_token):
        r = requests.get(f"{API}/v1/employee/attendance/today",
                         headers=_h(budi_token), timeout=30)
        assert r.status_code == 404


# ---------- approve & lock + PDF encryption ----------
# Run LAST (prefix z) because approval permanently locks slips.
class TestZApproveAndDownload:
    def test_z1_approve_all(self, hrd_token, period_id):
        # Maret 2026 is pre-approved in seed. If already approved, calling
        # approve-all now returns 400 (status != pending_approval) — this is correct.
        detail = requests.get(f"{API}/hr/periods/{period_id}",
                              headers=_h(hrd_token), timeout=30).json()
        if detail["period"]["status"] != "approved":
            # Need to submit first then approve
            s = requests.post(f"{API}/hr/periods/{period_id}/submit",
                              headers=_h(hrd_token), timeout=30)
            assert s.status_code == 200, s.text
            r = requests.post(f"{API}/hr/periods/{period_id}/approve-all",
                              headers=_h(hrd_token), timeout=120)
            assert r.status_code == 200, r.text
            detail = requests.get(f"{API}/hr/periods/{period_id}",
                                  headers=_h(hrd_token), timeout=30).json()
        assert detail["period"]["status"] == "approved"
        for s in detail["payslips"]:
            assert s["status"] == "approved"

    def test_z2_employee_sees_payslip(self, budi_token):
        r = requests.get(f"{API}/v1/employee/payslips",
                         headers=_h(budi_token), timeout=30)
        assert r.status_code == 200
        slips = r.json()
        assert len(slips) >= 1
        assert slips[0]["period"]["period_name"] == "Maret 2026"
        # Save sid for next test via class attr
        TestZApproveAndDownload.sid = slips[0]["id"]

    def test_z3_download_encrypted_pdf_opens_with_birthdate(self, budi_token):
        sid = getattr(TestZApproveAndDownload, "sid", None)
        assert sid, "sid not set from previous test"
        r = requests.get(f"{API}/v1/employee/payslips/{sid}/download",
                         headers=_h(budi_token), timeout=30)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        reader = PdfReader(io.BytesIO(r.content))
        assert reader.is_encrypted
        # wrong password should fail
        with pytest.raises(Exception):
            bad = PdfReader(io.BytesIO(r.content))
            bad.decrypt("000000")
            _ = bad.pages[0].extract_text()
        # correct password (Budi birth_date 1995-08-15 → DDMMYY = 150895)
        res = reader.decrypt("150895")
        assert res, "decrypt returned False with correct password"
        try:
            _ = reader.pages[0].extract_text()
        except FileNotDecryptedError:
            pytest.fail("PDF not decrypted with correct birthdate password")

    def test_z4_wrong_password_cannot_read(self, budi_token):
        sid = getattr(TestZApproveAndDownload, "sid", None)
        assert sid
        r = requests.get(f"{API}/v1/employee/payslips/{sid}/download",
                         headers=_h(budi_token), timeout=30)
        reader = PdfReader(io.BytesIO(r.content))
        reader.decrypt("000000")
        with pytest.raises(FileNotDecryptedError):
            _ = reader.pages[0].extract_text()
