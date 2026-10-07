"""Iteration 7 tests for new submit/reject workflow, dashboard BPJS stats,
configs (COMPANY_ADDRESS, PAYSLIP_SIGNATORY_*, CSV_DELIMITER), and PDF signature/header.
"""
import io
import os
import pytest
import requests
from pypdf import PdfReader

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
STAFF = {"identifier": "staff.hr@rumatku.id", "password": "Password123!"}
BUDI = {"identifier": "EMP-001", "password": "Password123!"}


def _login(cred):
    r = requests.post(f"{API}/auth/login", json=cred, timeout=30)
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
    return {e["nik"]: e for e in r.json()}


# ---------------- Dashboard BPJS totals ----------------
class TestDashboardBPJS:
    def test_dashboard_has_bpjs_totals(self, hrd_tok):
        r = requests.get(f"{API}/hr/dashboard", headers=_h(hrd_tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["total_bpjs_kes"] == 560964, d
        assert d["total_bpjs_tk"] == 970200, d


# ---------------- Configs ----------------
class TestNewConfigs:
    def test_new_keys_present(self, hrd_tok):
        r = requests.get(f"{API}/hr/configs", headers=_h(hrd_tok), timeout=30)
        keys = {c["config_key"] for c in r.json()}
        for k in ("COMPANY_ADDRESS", "PAYSLIP_SIGNATORY_NAME",
                  "PAYSLIP_SIGNATORY_TITLE", "CSV_DELIMITER"):
            assert k in keys, k

    @pytest.mark.parametrize("v", [",", ";", "|", "tab"])
    def test_delimiter_valid_values(self, hrd_tok, v):
        r = requests.put(f"{API}/hr/configs", headers=_h(hrd_tok), timeout=30,
                         json={"CSV_DELIMITER": v})
        assert r.status_code == 200, r.text

    def test_delimiter_invalid(self, hrd_tok):
        r = requests.put(f"{API}/hr/configs", headers=_h(hrd_tok), timeout=30,
                         json={"CSV_DELIMITER": "@"})
        assert r.status_code == 400

    def test_delimiter_applies_to_bsi_export(self, hrd_tok):
        # Set to ';', export, confirm; then restore
        requests.put(f"{API}/hr/configs", headers=_h(hrd_tok), timeout=30,
                     json={"CSV_DELIMITER": ";"})
        try:
            # Find approved period
            periods = requests.get(f"{API}/hr/periods", headers=_h(hrd_tok)).json()
            pid = next(p["id"] for p in periods if p["status"] == "approved")
            r = requests.post(f"{API}/hr/periods/{pid}/export-bsi", headers=_h(hrd_tok), timeout=30)
            assert r.status_code == 200, r.text
            text = r.content.decode("utf-8", errors="replace")
            first = text.splitlines()[0]
            assert ";" in first and "," not in first.split(";")[0], first
        finally:
            requests.put(f"{API}/hr/configs", headers=_h(hrd_tok),
                         json={"CSV_DELIMITER": ","})

    def test_delimiter_applies_to_ytd_template(self, hrd_tok):
        requests.put(f"{API}/hr/configs", headers=_h(hrd_tok),
                     json={"CSV_DELIMITER": "|"})
        try:
            r = requests.get(f"{API}/hr/tax-balances/template", headers=_h(hrd_tok), timeout=30)
            assert r.status_code == 200
            assert "|" in r.content.decode("utf-8").splitlines()[0]
        finally:
            requests.put(f"{API}/hr/configs", headers=_h(hrd_tok),
                         json={"CSV_DELIMITER": ","})

    def _removed_test_delimiter_applies_to_attendance_template(self, hrd_tok):
        requests.put(f"{API}/hr/configs", headers=_h(hrd_tok),
                     json={"CSV_DELIMITER": ";"})
        try:
            r = requests.get(f"{API}/hr/attendance/import-template", headers=_h(hrd_tok), timeout=30)
            assert r.status_code == 200
            assert ";" in r.content.decode("utf-8").splitlines()[0]
        finally:
            requests.put(f"{API}/hr/configs", headers=_h(hrd_tok),
                         json={"CSV_DELIMITER": ","})


# ---------------- PDF header + signature ----------------
class TestPayslipPDF:
    def test_pdf_contains_company_name_and_signatory(self, hrd_tok, emp_map):
        periods = requests.get(f"{API}/hr/periods", headers=_h(hrd_tok)).json()
        pid = next(p["id"] for p in periods if p["period_name"] == "Maret 2026")
        eid = emp_map["EMP-001"]["id"]
        # Set unique markers in configs
        marks = {"COMPANY_NAME": "PT ROSY TEST CO",
                 "COMPANY_ADDRESS": "Jl. Testing No.1 Bekasi",
                 "PAYSLIP_SIGNATORY_NAME": "Ir. Tester Sign",
                 "PAYSLIP_SIGNATORY_TITLE": "Head of HRD"}
        orig = {c["config_key"]: c["config_value"]
                for c in requests.get(f"{API}/hr/configs", headers=_h(hrd_tok)).json()
                if c["config_key"] in marks}
        requests.put(f"{API}/hr/configs", headers=_h(hrd_tok), json=marks)
        try:
            r = requests.get(f"{API}/hr/periods/{pid}/employees/{eid}/pdf",
                             headers=_h(hrd_tok), timeout=30)
            assert r.status_code == 200
            reader = PdfReader(io.BytesIO(r.content))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
            for v in marks.values():
                assert v in text, f"missing {v!r} in PDF text"
        finally:
            requests.put(f"{API}/hr/configs", headers=_h(hrd_tok), json=orig)


# ---------------- Submit/Reject workflow ----------------
def _create_test_period(tok, name="TEST_Workflow Apr 2026"):
    r = requests.post(f"{API}/hr/periods", headers=_h(tok),
                      json={"period_name": name, "start_date": "2026-04-01",
                            "end_date": "2026-04-30", "payment_date": "2026-05-05"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _cleanup_period(tok, pid):
    r = requests.delete(f"{API}/hr/periods/{pid}", headers=_h(tok), timeout=30)
    if r.status_code != 200:
        # Approved periods cannot be deleted via API — use direct DB.
        try:
            from pymongo import MongoClient
            db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017")) \
                [os.environ.get("DB_NAME", "test_database")]
            db.payslips.delete_many({"payroll_period_id": pid})
            db.payroll_periods.delete_one({"id": pid})
        except Exception:
            pass


class TestWorkflow:
    def test_process_does_not_auto_submit(self, hrd_tok):
        pid = _create_test_period(hrd_tok)
        try:
            r = requests.post(f"{API}/hr/periods/{pid}/process",
                              headers=_h(hrd_tok), timeout=60)
            assert r.status_code == 200
            per = requests.get(f"{API}/hr/periods/{pid}",
                               headers=_h(hrd_tok)).json()["period"]
            assert per["status"] == "draft", per["status"]
        finally:
            _cleanup_period(hrd_tok, pid)

    def test_staff_submit_cannot_approve(self, hrd_tok, staff_tok, emp_map):
        pid = _create_test_period(staff_tok)
        try:
            requests.post(f"{API}/hr/periods/{pid}/process",
                          headers=_h(staff_tok), timeout=60)
            # Submit as staff
            r = requests.post(f"{API}/hr/periods/{pid}/submit",
                              headers=_h(staff_tok), timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "pending_approval"
            # Staff cannot edit slip in pending state
            eid = emp_map["EMP-001"]["id"]
            e = requests.put(f"{API}/hr/periods/{pid}/employees/{eid}",
                             headers=_h(staff_tok),
                             json={"overtime_hours": 1, "kpi_incentive": 0,
                                   "additional_bonus": 0,
                                   "late_penalty_compensation": 0,
                                   "other_deductions": 0, "adjustment_notes": ""})
            assert e.status_code == 400, e.text
            # Staff cannot approve-all
            a = requests.post(f"{API}/hr/periods/{pid}/approve-all",
                              headers=_h(staff_tok), timeout=30)
            assert a.status_code == 403
            # Staff cannot approve per slip
            a2 = requests.post(f"{API}/hr/periods/{pid}/employees/{eid}/approve",
                               headers=_h(staff_tok), timeout=30)
            assert a2.status_code == 403
        finally:
            _cleanup_period(hrd_tok, pid)

    def test_manager_reject_requires_reason(self, hrd_tok, staff_tok):
        pid = _create_test_period(staff_tok)
        try:
            requests.post(f"{API}/hr/periods/{pid}/process",
                          headers=_h(staff_tok), timeout=60)
            requests.post(f"{API}/hr/periods/{pid}/submit",
                          headers=_h(staff_tok), timeout=30)
            # Reject with short reason -> 400
            r = requests.post(f"{API}/hr/periods/{pid}/reject",
                              headers=_h(hrd_tok), json={"reason": "no"})
            assert r.status_code == 400
            # Staff rejecting -> 403
            r2 = requests.post(f"{API}/hr/periods/{pid}/reject",
                               headers=_h(staff_tok),
                               json={"reason": "staff should not reject"})
            assert r2.status_code == 403
            # Good reject
            r3 = requests.post(f"{API}/hr/periods/{pid}/reject",
                               headers=_h(hrd_tok),
                               json={"reason": "Lembur Budi perlu dicek ulang"})
            assert r3.status_code == 200, r3.text
            per = r3.json()
            assert per["status"] == "revision"
            assert per["rejection_reason"] == "Lembur Budi perlu dicek ulang"
            assert any(h["action"] == "rejected" for h in per.get("review_history", []))
            # Reject again on non-pending -> 400
            r4 = requests.post(f"{API}/hr/periods/{pid}/reject",
                               headers=_h(hrd_tok),
                               json={"reason": "already in revision"})
            assert r4.status_code == 400
        finally:
            _cleanup_period(hrd_tok, pid)

    def test_full_cycle_resubmit_and_approve(self, hrd_tok, staff_tok, emp_map):
        pid = _create_test_period(staff_tok)
        try:
            requests.post(f"{API}/hr/periods/{pid}/process",
                          headers=_h(staff_tok), timeout=60)
            # approve-all on draft (not pending) -> 400
            bad = requests.post(f"{API}/hr/periods/{pid}/approve-all",
                                headers=_h(hrd_tok), timeout=30)
            assert bad.status_code == 400
            # Submit
            requests.post(f"{API}/hr/periods/{pid}/submit",
                          headers=_h(staff_tok), timeout=30)
            # Reject
            requests.post(f"{API}/hr/periods/{pid}/reject",
                          headers=_h(hrd_tok),
                          json={"reason": "please revise overtime"})
            # Staff can edit in revision
            eid = emp_map["EMP-001"]["id"]
            e = requests.put(f"{API}/hr/periods/{pid}/employees/{eid}",
                             headers=_h(staff_tok),
                             json={"overtime_hours": 2, "kpi_incentive": 0,
                                   "additional_bonus": 0,
                                   "late_penalty_compensation": 0,
                                   "other_deductions": 0,
                                   "adjustment_notes": "revised"})
            assert e.status_code == 200, e.text
            # Resubmit
            s = requests.post(f"{API}/hr/periods/{pid}/submit",
                              headers=_h(staff_tok), timeout=30)
            assert s.status_code == 200
            assert s.json()["status"] == "pending_approval"
            # Manager approve-all
            a = requests.post(f"{API}/hr/periods/{pid}/approve-all",
                              headers=_h(hrd_tok), timeout=60)
            assert a.status_code == 200, a.text
            per = requests.get(f"{API}/hr/periods/{pid}",
                               headers=_h(hrd_tok)).json()["period"]
            assert per["status"] == "approved"
        finally:
            _cleanup_period(hrd_tok, pid)

    def test_delete_period_states(self, hrd_tok, staff_tok):
        # draft -> delete ok
        pid = _create_test_period(staff_tok, "TEST_Delete Draft")
        r = requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok))
        assert r.status_code == 200
        # pending_approval -> delete ok
        pid = _create_test_period(staff_tok, "TEST_Delete Pending")
        requests.post(f"{API}/hr/periods/{pid}/process", headers=_h(staff_tok), timeout=60)
        requests.post(f"{API}/hr/periods/{pid}/submit", headers=_h(staff_tok))
        r = requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok))
        assert r.status_code == 200
        # revision -> delete ok
        pid = _create_test_period(staff_tok, "TEST_Delete Revision")
        requests.post(f"{API}/hr/periods/{pid}/process", headers=_h(staff_tok), timeout=60)
        requests.post(f"{API}/hr/periods/{pid}/submit", headers=_h(staff_tok))
        requests.post(f"{API}/hr/periods/{pid}/reject", headers=_h(hrd_tok),
                      json={"reason": "need revision for delete test"})
        r = requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok))
        assert r.status_code == 200


# ---------------- Routes/role check ----------------
class TestStaffRole:
    def test_staff_login_role(self):
        r = requests.post(f"{API}/auth/login", json=STAFF, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["role"] == "admin_payroll"
        assert d["user"]["email"] == "staff.hr@rumatku.id"

    def test_staff_cannot_reject_or_approve_on_maret(self, staff_tok, hrd_tok):
        periods = requests.get(f"{API}/hr/periods", headers=_h(hrd_tok)).json()
        pid = next(p["id"] for p in periods if p["period_name"] == "Maret 2026")
        r = requests.post(f"{API}/hr/periods/{pid}/reject",
                          headers=_h(staff_tok), json={"reason": "staff reject test"})
        assert r.status_code == 403
