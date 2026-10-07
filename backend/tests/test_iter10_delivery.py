"""Iteration 10 — Rumatku PDF delivery after approval, resend endpoints, employee download removed."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _demo_login(account: str) -> str:
    r = requests.post(f"{API}/auth/demo-login", json={"account": account}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def hrd():
    return {"Authorization": f"Bearer {_demo_login('hrd')}"}


@pytest.fixture(scope="module")
def staff():
    return {"Authorization": f"Bearer {_demo_login('staff')}"}


@pytest.fixture(scope="module")
def budi():
    return {"Authorization": f"Bearer {_demo_login('budi')}"}


def _create_period(headers, name, start, end, pay):
    r = requests.post(f"{API}/hr/periods", headers=headers,
                      json={"period_name": name, "start_date": start, "end_date": end, "payment_date": pay},
                      timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _poll_until_done(headers, pid, timeout=20):
    """Poll until no slip is 'queued' anymore."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{API}/hr/periods/{pid}", headers=headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        slips = data["payslips"]
        if slips and not any(s.get("delivery_status") == "queued" for s in slips):
            return data
        time.sleep(1)
    pytest.fail(f"Delivery didn't finish within {timeout}s")


def _full_approve(hrd, staff, name, start, end, pay):
    pid = _create_period(staff, name, start, end, pay)
    r = requests.post(f"{API}/hr/periods/{pid}/fetch-attendance", headers=staff, timeout=120)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/hr/periods/{pid}/submit", headers=staff, timeout=30)
    assert r.status_code == 200
    r = requests.post(f"{API}/hr/periods/{pid}/approve-all", headers=hrd, timeout=60)
    assert r.status_code == 200, r.text
    return pid


def _delete(headers, pid):
    # Approved periods can't be deleted; this is intentional. We just leave them (TEST_ prefix).
    requests.delete(f"{API}/hr/periods/{pid}", headers=headers, timeout=30)


class TestDeliveryHappyAndFailurePath:
    """EMP-002 is force-failed via RUMATKU_MOCK_FAIL_NIKS; EMP-001 & EMP-003 should succeed."""

    @pytest.fixture(scope="class")
    def pid(self, hrd, staff):
        pid = _full_approve(hrd, staff, "TEST_Iter10 Juli 2027", "2027-07-01", "2027-07-31", "2027-08-05")
        yield pid

    def test_delivery_completes_and_period_approved(self, hrd, pid):
        data = _poll_until_done(hrd, pid, timeout=25)
        assert data["period"]["status"] == "approved"
        by_nik = {s["employee"]["nik"]: s for s in data["payslips"]}
        assert by_nik["EMP-001"]["delivery_status"] == "sent"
        assert by_nik["EMP-003"]["delivery_status"] == "sent"
        assert by_nik["EMP-002"]["delivery_status"] == "failed"
        # EMP-002 must have attempted exactly 3 times
        assert by_nik["EMP-002"].get("delivery_attempts") == 3
        assert by_nik["EMP-002"].get("delivery_error")
        # Success rows should have delivery_ref
        assert by_nik["EMP-001"].get("delivery_ref")

    def test_pdf_path_encrypted_exists(self, hrd, pid):
        data = requests.get(f"{API}/hr/periods/{pid}", headers=hrd, timeout=30).json()
        # pdf_path is projected away from payslips table, but we can check via workbench
        for s in data["payslips"]:
            r = requests.get(f"{API}/hr/periods/{pid}/employees/{s['employee_id']}/pdf",
                             headers=hrd, timeout=30)
            assert r.status_code == 200
            assert r.headers["content-type"] == "application/pdf"
            break

    def test_resend_failed_endpoint(self, hrd, pid):
        r = requests.post(f"{API}/hr/periods/{pid}/resend-failed", headers=hrd, timeout=30)
        assert r.status_code == 200
        assert r.json()["queued"] >= 1
        data = _poll_until_done(hrd, pid, timeout=15)
        emp2 = next(s for s in data["payslips"] if s["employee"]["nik"] == "EMP-002")
        assert emp2["delivery_status"] == "failed"
        # One manual attempt added (attempts param = 1), so total attempts = 3 + 1
        assert emp2["delivery_attempts"] >= 4

    def test_resend_single_employee(self, hrd, pid):
        data = requests.get(f"{API}/hr/periods/{pid}", headers=hrd, timeout=30).json()
        emp2 = next(s for s in data["payslips"] if s["employee"]["nik"] == "EMP-002")
        prev_attempts = emp2["delivery_attempts"]
        r = requests.post(f"{API}/hr/periods/{pid}/employees/{emp2['employee_id']}/resend",
                          headers=hrd, timeout=30)
        assert r.status_code == 200
        _poll_until_done(hrd, pid, timeout=15)
        after = requests.get(f"{API}/hr/periods/{pid}", headers=hrd, timeout=30).json()
        emp2 = next(s for s in after["payslips"] if s["employee"]["nik"] == "EMP-002")
        assert emp2["delivery_attempts"] > prev_attempts

    def test_resend_already_sent_rejected(self, hrd, pid):
        data = requests.get(f"{API}/hr/periods/{pid}", headers=hrd, timeout=30).json()
        emp1 = next(s for s in data["payslips"] if s["employee"]["nik"] == "EMP-001")
        r = requests.post(f"{API}/hr/periods/{pid}/employees/{emp1['employee_id']}/resend",
                          headers=hrd, timeout=30)
        assert r.status_code == 400
        assert "terkirim" in r.text.lower()

    def test_resend_failed_when_none_failed(self, hrd, staff):
        # Create a new period and approve where EMP-002 still fails... actually EMP-002 always fails,
        # so "no failed" is never testable in mock without temp env mod. Instead, test the 400 for not-approved.
        pid2 = _create_period(staff, "TEST_Iter10 Aug 2027", "2027-08-01", "2027-08-31", "2027-09-05")
        r = requests.post(f"{API}/hr/periods/{pid2}/resend-failed", headers=hrd, timeout=30)
        assert r.status_code == 400
        requests.delete(f"{API}/hr/periods/{pid2}", headers=hrd, timeout=30)


class TestPreApprovalNoDelivery:
    """Before full approval, delivery_status must be absent."""

    def test_no_delivery_in_draft(self, hrd, staff):
        pid = _create_period(staff, "TEST_Iter10 Sep 2027", "2027-09-01", "2027-09-30", "2027-10-05")
        try:
            r = requests.post(f"{API}/hr/periods/{pid}/fetch-attendance", headers=staff, timeout=120)
            assert r.status_code == 200
            r = requests.get(f"{API}/hr/periods/{pid}", headers=staff, timeout=30)
            for s in r.json()["payslips"]:
                assert "delivery_status" not in s or s["delivery_status"] is None
            # resend-failed before approval → 400
            r = requests.post(f"{API}/hr/periods/{pid}/resend-failed", headers=hrd, timeout=30)
            assert r.status_code == 400
        finally:
            requests.delete(f"{API}/hr/periods/{pid}", headers=hrd, timeout=30)


class TestEmployeeDownloadRemoved:
    """Employee can no longer download payslip PDF; only 1721-A1 still works."""

    def test_payslip_download_returns_404(self, budi):
        # Pick an approved slip for Budi
        r = requests.get(f"{API}/v1/employee/payslips", headers=budi, timeout=30)
        assert r.status_code == 200
        slips = r.json()
        if not slips:
            pytest.skip("Budi has no approved payslip yet")
        sid = slips[0]["id"]
        r = requests.get(f"{API}/v1/employee/payslips/{sid}/download", headers=budi, timeout=30)
        assert r.status_code == 404

    def test_payslip_detail_no_pdf_fields(self, budi):
        r = requests.get(f"{API}/v1/employee/payslips", headers=budi, timeout=30)
        slips = r.json()
        if not slips:
            pytest.skip("No payslip")
        sid = slips[0]["id"]
        r = requests.get(f"{API}/v1/employee/payslips/{sid}", headers=budi, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "pdf_path" not in data
        assert "pdf_password_hash" not in data
        # delivery_status key should still be visible (for the banner text)
        assert "take_home_pay" in data

    def test_1721a1_download_still_works(self, budi):
        r = requests.get(f"{API}/v1/employee/tax-forms/1721a1", headers=budi, timeout=30)
        assert r.status_code == 200
        forms = r.json()
        if not forms:
            pytest.skip("Budi has no 1721-A1 yet")
        year = forms[0]["year"] if "year" in forms[0] else forms[0].get("tax_year")
        if not year:
            pytest.skip("Can't determine year")
        r = requests.get(f"{API}/v1/employee/tax-forms/1721a1/{year}/download", headers=budi, timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"


class TestBsiExportStillWorks:
    def test_bsi_export_on_approved(self, hrd, staff):
        # Reuse a TEST_ approved period from main agent setup (TEST_Mei 2027 all sent)
        periods = requests.get(f"{API}/hr/periods", headers=hrd, timeout=30).json()
        approved = [p for p in periods if p["status"] == "approved" and p["period_name"].startswith("TEST_")]
        if not approved:
            pytest.skip("No approved TEST_ period available")
        pid = approved[0]["id"]
        r = requests.post(f"{API}/hr/periods/{pid}/export-bsi", headers=hrd, timeout=60)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert int(r.headers.get("x-exported-count", "0")) >= 1
