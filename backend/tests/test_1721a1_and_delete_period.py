"""Tests for new features: Bukti Potong 1721-A1 (HRD + Employee) and Delete Draft Period."""
import io
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
HR_EMAIL = "hrd.manager@rumatku.id"
EMP_LOGIN = "EMP-001"
PWD = "Password123!"


@pytest.fixture(scope="module")
def hr_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"identifier": HR_EMAIL, "password": PWD})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def emp_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"identifier": EMP_LOGIN, "password": PWD})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def budi_id(hr_client):
    r = hr_client.get(f"{BASE_URL}/api/hr/employees")
    assert r.status_code == 200
    for e in r.json():
        if e["nik"] == "EMP-001":
            return e["id"]
    pytest.fail("EMP-001 not found")


# ---------- HRD: 1721-A1 listing (no YTD) ----------
class TestA1ListNoYtd:
    def test_list_returns_budi_for_2026(self, hr_client, budi_id):
        # Make sure no YTD for Budi 2026
        bals = hr_client.get(f"{BASE_URL}/api/hr/tax-balances?year=2026").json()
        for b in bals:
            if b.get("nik") == "EMP-001":
                hr_client.delete(f"{BASE_URL}/api/hr/tax-balances/{b['id']}")

        r = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1?year=2026")
        assert r.status_code == 200
        rows = r.json()
        budi = next((x for x in rows if x["nik"] == "EMP-001"), None)
        assert budi is not None, f"Budi missing from {rows}"
        # Expected per spec (Maret 2026 only approved)
        it = budi["items"]
        assert round(it["i1"] + it["i3"] + it["i5"] + it["i7"]) == 8312400, f"bruto wrong: {it}"
        assert round(it["i8"]) == 8312400
        assert round(it["i9"]) == 415620, f"biaya jabatan: {it['i9']}"
        assert round(it["i20"]) == 83124, f"pph dipotong: {it['i20']}"
        assert budi["masa_start"] == 3 and budi["masa_end"] == 3
        assert budi["months_worked"] == 1
        assert budi["is_complete"] is False
        # number format
        assert budi["number"].startswith("1.1-03.26-")
        assert len(budi["number"].split("-")[-1]) == 7

    def test_pdf_download_unencrypted(self, hr_client, budi_id):
        r = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1/{budi_id}/pdf?year=2026")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
        # Not encrypted
        assert b"/Encrypt" not in r.content[:4096]

    def test_pdf_404_for_year_no_slips(self, hr_client, budi_id):
        r = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1/{budi_id}/pdf?year=2020")
        assert r.status_code == 404


# ---------- HRD: with YTD initial balance ----------
class TestA1WithYtd:
    @pytest.fixture(scope="class")
    def ytd_setup(self, hr_client):
        csv_content = (
            "nik,tax_year,cutoff_month,ptkp_status,gross_income_ytd,employee_jht_jp_ytd,"
            "biaya_jabatan_ytd,pph21_paid_ytd,notes\n"
            "EMP-001,2026,2,K/1,16000000,360000,800000,160000,TEST\n"
        )
        files = {"file": ("ytd.csv", csv_content.encode(), "text/csv")}
        r = hr_client.post(f"{BASE_URL}/api/hr/tax-balances/import", files=files)
        assert r.status_code == 200, r.text
        yield
        # cleanup
        bals = hr_client.get(f"{BASE_URL}/api/hr/tax-balances?year=2026").json()
        for b in bals:
            if b.get("nik") == "EMP-001":
                hr_client.delete(f"{BASE_URL}/api/hr/tax-balances/{b['id']}")

    def test_includes_i7a_and_sums_correct(self, hr_client, ytd_setup):
        r = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1?year=2026")
        budi = next(x for x in r.json() if x["nik"] == "EMP-001")
        it = budi["items"]
        assert round(it["i7a"]) == 16000000
        # i8 = i1..i7a
        s = sum(it[k] for k in ("i1", "i2", "i3", "i4", "i5", "i6", "i7", "i7a"))
        assert round(it["i8"]) == round(s)
        # i11 = i9 + i10
        assert round(it["i11"]) == round(it["i9"] + it["i10"])
        # i12 = i8 - i11
        assert round(it["i12"]) == round(it["i8"] - it["i11"])
        # i16 PKP rounded down to thousands
        assert it["i16"] % 1000 == 0
        # masa_start = 1 when YTD imported
        assert budi["masa_start"] == 1
        assert budi["has_initial_balance"] is True


# ---------- Employee self-service ----------
class TestEmployeeA1:
    def test_list_shows_2026(self, emp_client):
        r = emp_client.get(f"{BASE_URL}/api/v1/employee/tax-forms/1721a1")
        assert r.status_code == 200
        years = [x["tax_year"] for x in r.json()]
        assert 2026 in years

    def test_download_encrypted_with_birth_password(self, emp_client):
        r = emp_client.get(f"{BASE_URL}/api/v1/employee/tax-forms/1721a1/2026/download")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        # Should be encrypted - try opening with password 150895
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        assert reader.is_encrypted
        assert reader.decrypt("150895") != 0

    def test_download_404_no_slips_year(self, emp_client):
        r = emp_client.get(f"{BASE_URL}/api/v1/employee/tax-forms/1721a1/2020/download")
        assert r.status_code == 404

    def test_employee_cannot_access_hr_endpoint(self, emp_client, budi_id):
        r = emp_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1/{budi_id}/pdf?year=2026")
        assert r.status_code in (401, 403)


# ---------- Delete period ----------
class TestDeletePeriod:
    def test_delete_draft_period(self, hr_client):
        name = f"TEST_DeleteMe_{uuid.uuid4().hex[:6]}"
        r = hr_client.post(f"{BASE_URL}/api/hr/periods", json={
            "period_name": name, "start_date": "2027-01-01", "end_date": "2027-01-31",
            "payment_date": "2027-02-05"})
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        # process to create draft slips
        hr_client.post(f"{BASE_URL}/api/hr/periods/{pid}/process")
        # delete
        d = hr_client.delete(f"{BASE_URL}/api/hr/periods/{pid}")
        assert d.status_code == 200, d.text
        assert d.json()["ok"] is True
        # verify gone
        g = hr_client.get(f"{BASE_URL}/api/hr/periods/{pid}")
        assert g.status_code == 404

    def test_cannot_delete_approved_maret(self, hr_client):
        periods = hr_client.get(f"{BASE_URL}/api/hr/periods").json()
        maret = next((p for p in periods if "Maret 2026" in p["period_name"]), None)
        if not maret:
            pytest.skip("Maret 2026 not found")
        r = hr_client.delete(f"{BASE_URL}/api/hr/periods/{maret['id']}")
        assert r.status_code == 400


# ---------- NPWP on employee (REMOVED iter9 — PUT /hr/employees deleted) ----------
class _TestEmployeeNpwp_REMOVED:
    def test_npwp_persists_and_appears_in_pdf(self, hr_client, budi_id):
        # Get current emp
        emps = hr_client.get(f"{BASE_URL}/api/hr/employees").json()
        orig = next(e for e in emps if e["id"] == budi_id)
        original_npwp = orig.get("npwp", "") or ""
        test_npwp = "99.888.777.6-123.000"
        try:
            payload = {**{k: orig.get(k) for k in orig if k not in ("id", "created_at", "updated_at")}}
            payload["npwp"] = test_npwp
            r = hr_client.put(f"{BASE_URL}/api/hr/employees/{budi_id}", json=payload)
            assert r.status_code == 200, r.text
            # Verify persisted
            emps2 = hr_client.get(f"{BASE_URL}/api/hr/employees").json()
            b2 = next(e for e in emps2 if e["id"] == budi_id)
            assert b2["npwp"] == test_npwp
            # Verify in A1 listing
            rows = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1?year=2026").json()
            budi = next(x for x in rows if x["nik"] == "EMP-001")
            assert budi["npwp"] == test_npwp
            # Verify in PDF - extract text with pypdf (reportlab compresses streams)
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            pdf = hr_client.get(f"{BASE_URL}/api/hr/tax-forms/1721a1/{budi_id}/pdf?year=2026").content
            reader = PdfReader(io.BytesIO(pdf))
            text = "".join(p.extract_text() or "" for p in reader.pages)
            assert test_npwp in text, f"NPWP not in PDF text: {text[:500]}"
        finally:
            # restore
            payload["npwp"] = original_npwp
            hr_client.put(f"{BASE_URL}/api/hr/employees/{budi_id}", json=payload)


# ---------- Regression: existing endpoints still fine ----------
class TestRegression:
    def test_login_me(self, hr_client):
        r = hr_client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200

    def test_periods_list(self, hr_client):
        r = hr_client.get(f"{BASE_URL}/api/hr/periods")
        assert r.status_code == 200

    def test_employee_payslips(self, emp_client):
        r = emp_client.get(f"{BASE_URL}/api/v1/employee/payslips")
        assert r.status_code == 200
