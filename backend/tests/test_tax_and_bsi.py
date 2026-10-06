"""Backend tests for new features (iteration 2):
- POST /api/hr/periods/{pid}/export-bsi (BSI CSV export, column format, 400 when none approved)
- /api/hr/tax-balances (template, import csv/semicolon/xlsx, unknown NIK error, cutoff validation, delete)
- December reconciliation (Pasal 17) via build_slip + /process on a December period
"""
import csv
import io
import os
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}


def _h(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def hrd_token():
    r = requests.post(f"{API}/auth/login", json=HRD, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def employees(hrd_token):
    r = requests.get(f"{API}/hr/employees", headers=_h(hrd_token), timeout=30)
    assert r.status_code == 200
    return {e["nik"]: e for e in r.json()}


@pytest.fixture(scope="module")
def maret_pid(hrd_token):
    r = requests.get(f"{API}/hr/periods", headers=_h(hrd_token), timeout=30)
    for p in r.json():
        if p["period_name"] == "Maret 2026":
            return p["id"]
    pytest.skip("Maret 2026 not found")


# ---------- BSI export ----------
class TestBsiExport:
    def test_export_bsi_maret_csv(self, hrd_token, maret_pid):
        r = requests.post(f"{API}/hr/periods/{maret_pid}/export-bsi",
                          headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        cd = r.headers.get("content-disposition", "")
        assert "BSI_Payroll_Maret_2026.csv" in cd
        # headers X-Exported-Count / X-Skipped-Niks
        skipped = r.headers.get("x-skipped-niks", "")
        assert "EMP-003" in skipped, f"Dimas (unpaid) should be skipped, got '{skipped}'"
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["Rekening Debet", "Rekening Kredit", "Nama Penerima",
                           "Nominal", "Berita Acara", "Email"]
        body = {row[2]: row for row in rows[1:]}
        assert "Budi Santoso" in body
        budi = body["Budi Santoso"]
        assert int(budi[3]) == 7716876, budi
        siti = body.get("Siti Aminah")
        assert siti and int(siti[3]) == 5517934, siti
        # No Dimas row (skipped)
        assert "Dimas Pratama" not in body

    def test_export_bsi_no_approved_returns_400(self, hrd_token):
        # Create a fresh period with no approved slips
        pr = requests.post(f"{API}/hr/periods", headers=_h(hrd_token), timeout=30,
                           json={"period_name": "TEST_BSI_empty",
                                 "start_date": "2026-05-01", "end_date": "2026-05-31",
                                 "payment_date": "2026-06-05"})
        assert pr.status_code == 200, pr.text
        pid = pr.json()["id"]
        r = requests.post(f"{API}/hr/periods/{pid}/export-bsi",
                          headers=_h(hrd_token), timeout=30)
        assert r.status_code == 400


# ---------- Tax YTD balances ----------
class TestTaxBalances:
    created_ids = []

    def test_template_download(self, hrd_token):
        r = requests.get(f"{API}/hr/tax-balances/template", headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        header = r.text.splitlines()[0]
        for col in ("nik", "tax_year", "cutoff_month", "ptkp_status",
                    "gross_income_ytd", "pph21_paid_ytd"):
            assert col in header

    def test_import_csv_comma(self, hrd_token, employees):
        csvbody = (
            "nik,tax_year,cutoff_month,ptkp_status,gross_income_ytd,"
            "employee_jht_jp_ytd,biaya_jabatan_ytd,pph21_paid_ytd,notes\n"
            "EMP-001,2026,11,K/1,91436400,1980000,4571820,914364,TEST comma\n"
        )
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.csv", csvbody, "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["imported"] == 1, d
        assert d["errors"] == []
        # list and record id for cleanup
        lst = requests.get(f"{API}/hr/tax-balances", headers=_h(hrd_token),
                           params={"year": 2026}, timeout=30).json()
        row = next(x for x in lst if x["nik"] == "EMP-001")
        assert row["cutoff_month"] == 11
        assert row["gross_income_ytd"] == 91436400
        assert row["pph21_paid_ytd"] == 914364
        TestTaxBalances.budi_ytd_id = row["id"]

    def test_import_csv_semicolon_eu_numbers(self, hrd_token, employees):
        # Semicolon delimiter, European number formatting (dots as thousand sep)
        csvbody = (
            "nik;tax_year;cutoff_month;ptkp_status;gross_income_ytd;"
            "employee_jht_jp_ytd;biaya_jabatan_ytd;pph21_paid_ytd;notes\n"
            "EMP-002;2026;11;TK/0;50.000.000;1.000.000;2.500.000;250.000;TEST semicolon\n"
        )
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.csv", csvbody, "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 1
        lst = requests.get(f"{API}/hr/tax-balances", headers=_h(hrd_token),
                           params={"year": 2026}, timeout=30).json()
        row = next(x for x in lst if x["nik"] == "EMP-002")
        assert row["gross_income_ytd"] == 50000000, row
        TestTaxBalances.siti_ytd_id = row["id"]

    def test_import_unknown_nik_error(self, hrd_token):
        csvbody = ("nik,tax_year,cutoff_month,ptkp_status,gross_income_ytd,"
                   "employee_jht_jp_ytd,biaya_jabatan_ytd,pph21_paid_ytd,notes\n"
                   "EMP-999,2026,6,K/0,1,1,1,1,TEST unknown\n")
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.csv", csvbody, "text/csv")})
        assert r.status_code == 200
        d = r.json()
        assert d["imported"] == 0
        assert any("EMP-999" in e for e in d["errors"])

    def test_import_cutoff_out_of_range(self, hrd_token):
        csvbody = ("nik,tax_year,cutoff_month,ptkp_status,gross_income_ytd,"
                   "employee_jht_jp_ytd,biaya_jabatan_ytd,pph21_paid_ytd,notes\n"
                   "EMP-001,2026,12,K/1,1,1,1,1,TEST bad cutoff\n")
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.csv", csvbody, "text/csv")})
        assert r.status_code == 200
        d = r.json()
        assert d["imported"] == 0
        assert any("cutoff" in e.lower() for e in d["errors"]), d["errors"]

    def test_import_xlsx(self, hrd_token):
        try:
            from openpyxl import Workbook
        except ImportError:
            pytest.skip("openpyxl not available")
        wb = Workbook()
        ws = wb.active
        ws.append(["nik", "tax_year", "cutoff_month", "ptkp_status", "gross_income_ytd",
                   "employee_jht_jp_ytd", "biaya_jabatan_ytd", "pph21_paid_ytd", "notes"])
        ws.append(["EMP-001", 2026, 11, "K/1", 91436400, 1980000, 4571820, 914364, "TEST xlsx"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.xlsx", buf.read(),
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 1


# ---------- December reconciliation ----------
class TestDecemberReconciliation:
    pid = None
    ytd_id = None

    def test_a_setup_ytd(self, hrd_token):
        """Ensure Budi YTD row exists on this worker regardless of class scheduling."""
        csvbody = (
            "nik,tax_year,cutoff_month,ptkp_status,gross_income_ytd,"
            "employee_jht_jp_ytd,biaya_jabatan_ytd,pph21_paid_ytd,notes\n"
            "EMP-001,2026,11,K/1,91436400,1980000,4571820,914364,TEST dec recon\n"
        )
        r = requests.post(f"{API}/hr/tax-balances/import",
                          headers=_h(hrd_token), timeout=30,
                          files={"file": ("ytd.csv", csvbody, "text/csv")})
        assert r.status_code == 200 and r.json()["imported"] == 1, r.text
        lst = requests.get(f"{API}/hr/tax-balances", headers=_h(hrd_token),
                           params={"year": 2026}, timeout=30).json()
        TestDecemberReconciliation.ytd_id = next(x["id"] for x in lst if x["nik"] == "EMP-001")

    def test_create_december_period_and_process(self, hrd_token):
        pr = requests.post(f"{API}/hr/periods", headers=_h(hrd_token), timeout=30,
                           json={"period_name": "TEST_Desember 2026",
                                 "start_date": "2026-12-01", "end_date": "2026-12-31",
                                 "payment_date": "2027-01-05"})
        assert pr.status_code == 200, pr.text
        TestDecemberReconciliation.pid = pr.json()["id"]
        proc = requests.post(f"{API}/hr/periods/{TestDecemberReconciliation.pid}/process",
                             headers=_h(hrd_token), timeout=120)
        assert proc.status_code == 200, proc.text

    def test_budi_pasal17_reconciliation(self, hrd_token, employees):
        pid = TestDecemberReconciliation.pid
        eid = employees["EMP-001"]["id"]
        r = requests.get(f"{API}/hr/periods/{pid}/employees/{eid}",
                         headers=_h(hrd_token), timeout=30)
        assert r.status_code == 200, r.text
        s = r.json()["payslip"]
        assert s["pph21_method"] == "pasal17", s.get("pph21_method")
        recon = s["tax_reconciliation"]
        assert recon is not None, "tax_reconciliation missing"
        assert recon["gross_year"] == 99908800, recon
        assert recon["biaya_jabatan"] == 4995440, recon
        assert recon["jht_jp_year"] == 2160000, recon
        assert recon["neto_year"] == 92753360, recon
        assert recon["ptkp_amount"] == 63000000, recon
        assert recon["pkp"] == 29753000, recon
        assert recon["annual_tax"] == 1487650, recon
        assert s["pph21_amount"] == 573286, s["pph21_amount"]

    def test_non_december_still_ter(self, hrd_token, employees, maret_pid):
        eid = employees["EMP-001"]["id"]
        r = requests.get(f"{API}/hr/periods/{maret_pid}/employees/{eid}",
                         headers=_h(hrd_token), timeout=30).json()
        # Stored Maret slip may predate pph21_method field; absence == TER
        assert r["payslip"].get("pph21_method", "ter") == "ter"
        assert r["payslip"].get("tax_reconciliation") is None


# ---------- Cleanup YTD rows ----------
def test_zzz_cleanup_ytd_rows(hrd_token):
    for attr in ("budi_ytd_id", "siti_ytd_id"):
        bid = getattr(TestTaxBalances, attr, None)
        if bid:
            r = requests.delete(f"{API}/hr/tax-balances/{bid}",
                                headers=_h(hrd_token), timeout=30)
            assert r.status_code == 200, r.text
