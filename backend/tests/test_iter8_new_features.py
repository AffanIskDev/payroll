"""Iteration 8: notifications, UNIT_MINGGU schedule, overtime recap, employee ot_rate default."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
STAFF = {"identifier": "staff.hr@rumatku.id", "password": "Password123!"}


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


# ------- UNIT_MINGGU schedule -------
class TestUnitMingguSchedule:
    def test_unit_minggu_has_two_shifts(self, hrd_tok):
        r = requests.get(f"{API}/hr/schedules", headers=_h(hrd_tok), timeout=30)
        assert r.status_code == 200, r.text
        s = next(x for x in r.json() if x["code"] == "UNIT_MINGGU")
        codes = {sh["code"] for sh in s["shifts"]}
        assert codes == {"S1", "S2"}, codes
        s1 = next(sh for sh in s["shifts"] if sh["code"] == "S1")
        s2 = next(sh for sh in s["shifts"] if sh["code"] == "S2")
        # S1 Mon-Fri 07-15, Sat 08-14, Sun off
        for wd in ("0", "1", "2", "3", "4"):
            assert s1["days"][wd] == {"start": "07:00", "end": "15:00"}
        assert s1["days"].get("5") == {"start": "08:00", "end": "14:00"}
        assert "6" not in s1["days"] or not s1["days"].get("6", {}).get("start")
        # S2 Mon-Fri 13-21, Sat off, Sun 08-14
        for wd in ("0", "1", "2", "3", "4"):
            assert s2["days"][wd] == {"start": "13:00", "end": "21:00"}
        assert "5" not in s2["days"] or not s2["days"].get("5", {}).get("start")
        assert s2["days"].get("6") == {"start": "08:00", "end": "14:00"}

    def test_unit_minggu_attendance_shift_detection(self, hrd_tok):
        import pymongo
        mc = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        mdb = mc[os.environ.get("DB_NAME", "test_database")]
        mdb.users.delete_many({"email": "test.um01@rumatku.id"})
        mdb.employees.delete_many({"nik": "TEST_UM01"})
        emps = requests.get(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30).json()
        # Create or find a TEST_ employee on UNIT_MINGGU
        emp = next((e for e in emps if e["nik"] == "TEST_UM01"), None)
        created_id = None
        if not emp:
            payload = {"nik": "TEST_UM01", "name": "TEST Minggu Worker",
                       "email": "test.um01@rumatku.id", "department": "Operations",
                       "position": "Staff", "basic_salary": 5000000,
                       "ptkp_status": "TK/0", "work_schedule_code": "UNIT_MINGGU",
                       "join_date": "2026-01-01", "birth_date": "1995-01-01",
                       "gender": "L", "marital_status": "TK",
                       "password": "Password123!", "overtime_hourly_rate": 0}
            r = requests.post(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30, json=payload)
            assert r.status_code in (200, 201), r.text
            emp = r.json()
            created_id = emp["id"]
        try:
            eid = emp["id"]
            # Sunday 2026-04-05: S2 start 08:00 → 08:10 = late 10
            cases = [
                ("2026-04-05", "08:10", "14:00", "S2", 10),  # Sunday
                ("2026-04-04", "08:00", "14:00", "S1", 0),   # Saturday
                ("2026-04-06", "13:05", "21:00", "S2", 5),   # Monday
            ]
            log_ids = []
            try:
                for wd, cin, cout, exp_code, exp_late in cases:
                    r = requests.post(f"{API}/hr/attendance", headers=_h(hrd_tok), timeout=30,
                                      json={"employee_id": eid, "work_date": wd,
                                            "check_in_time": cin, "check_out_time": cout,
                                            "leave_type": "present"})
                    assert r.status_code == 200, f"{wd}: {r.text}"
                    log = r.json()
                    log_ids.append(log["id"])
                    assert log["shift_code"] == exp_code, f"{wd}: expected {exp_code} got {log.get('shift_code')}"
                    assert log["minutes_late"] == exp_late, f"{wd}: late {log['minutes_late']} vs {exp_late}"
            finally:
                for lid in log_ids:
                    requests.delete(f"{API}/hr/attendance/{lid}", headers=_h(hrd_tok), timeout=30)
        finally:
            if created_id:
                requests.delete(f"{API}/hr/employees/{created_id}", headers=_h(hrd_tok), timeout=30)
                mdb.users.delete_many({"email": "test.um01@rumatku.id"})


# ------- Notifications -------
def _find_period(tok, name):
    r = requests.get(f"{API}/hr/periods", headers=_h(tok), timeout=30)
    for p in r.json():
        if p["period_name"] == name:
            return p
    return None


class TestNotifications:
    def test_notifications_submit_reject_flow(self, hrd_tok, staff_tok):
        pname = "TEST_Notif Aug 2026"
        # Clean any stale
        old = _find_period(hrd_tok, pname)
        if old:
            requests.delete(f"{API}/hr/periods/{old['id']}", headers=_h(hrd_tok), timeout=30)

        # Staff creates period
        r = requests.post(f"{API}/hr/periods", headers=_h(staff_tok), timeout=30,
                          json={"period_name": pname, "start_date": "2026-08-01",
                                "end_date": "2026-08-31", "payment_date": "2026-09-05"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        try:
            # Process + submit
            r = requests.post(f"{API}/hr/periods/{pid}/process", headers=_h(staff_tok), timeout=60)
            assert r.status_code == 200, r.text
            r = requests.post(f"{API}/hr/periods/{pid}/submit", headers=_h(staff_tok), timeout=30)
            assert r.status_code == 200, r.text

            # Manager notifications includes 'submitted' entry for this period
            notes = requests.get(f"{API}/hr/notifications", headers=_h(hrd_tok), timeout=30).json()
            m = [n for n in notes if n["period_id"] == pid]
            assert len(m) == 1
            assert m[0]["kind"] == "submitted"
            assert m[0]["by"] == "staff.hr@rumatku.id"
            assert m[0]["at"]

            # Staff notifications should NOT include this (not yet rejected)
            snotes = requests.get(f"{API}/hr/notifications", headers=_h(staff_tok), timeout=30).json()
            assert not any(n["period_id"] == pid for n in snotes)

            # Manager rejects
            reason = "TEST reject reason iter8"
            r = requests.post(f"{API}/hr/periods/{pid}/reject", headers=_h(hrd_tok), timeout=30,
                              json={"reason": reason})
            assert r.status_code == 200, r.text

            # Now manager should not see it; staff should see rejected notice with reason
            notes2 = requests.get(f"{API}/hr/notifications", headers=_h(hrd_tok), timeout=30).json()
            assert not any(n["period_id"] == pid for n in notes2)
            snotes2 = requests.get(f"{API}/hr/notifications", headers=_h(staff_tok), timeout=30).json()
            m2 = [n for n in snotes2 if n["period_id"] == pid]
            assert len(m2) == 1
            assert m2[0]["kind"] == "rejected"
            assert m2[0]["reason"] == reason
        finally:
            requests.delete(f"{API}/hr/periods/{pid}", headers=_h(hrd_tok), timeout=30)


# ------- Overtime recap -------
class TestOvertimeRecap:
    def test_overtime_recap_maret(self, hrd_tok):
        r = requests.get(f"{API}/hr/overtime-recap", headers=_h(hrd_tok), timeout=30,
                         params={"month": "2026-03"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["month"] == "2026-03"
        assert isinstance(d["rows"], list)
        assert len(d["rows"]) >= 1
        # Each row has required fields
        for row in d["rows"]:
            for k in ("nik", "name", "period_name", "overtime_hours", "overtime_rate",
                     "overtime_pay", "slip_status"):
                assert k in row, (k, row)
        # Budi should have rate 50000 in seed
        budi = next((r_ for r_ in d["rows"] if r_["nik"] == "EMP-001"), None)
        assert budi is not None
        assert budi["overtime_rate"] == 50000, budi
        # totals match
        assert d["total_hours"] == sum(r_["overtime_hours"] for r_ in d["rows"])
        assert d["total_pay"] == sum(r_["overtime_pay"] for r_ in d["rows"])

    def test_overtime_recap_bad_month(self, hrd_tok):
        r = requests.get(f"{API}/hr/overtime-recap", headers=_h(hrd_tok), timeout=30,
                         params={"month": "bogus"})
        assert r.status_code == 400


# ------- Employee overtime_hourly_rate -------
class TestEmployeeOvertimeRate:
    def test_default_zero_on_create(self, hrd_tok):
        import pymongo
        # Pre-clean any orphan user from prior runs
        mc = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        mdb = mc[os.environ.get("DB_NAME", "test_database")]
        mdb.users.delete_many({"email": "test.otr1@rumatku.id"})
        mdb.employees.delete_many({"nik": "TEST_OTR1"})
        payload = {"nik": "TEST_OTR1", "name": "TEST OT Rate",
                   "email": "test.otr1@rumatku.id", "department": "Ops",
                   "position": "Staff", "basic_salary": 5000000,
                   "ptkp_status": "TK/0", "work_schedule_code": "KANTOR_PUSAT",
                   "join_date": "2026-01-01", "birth_date": "1995-01-01",
                   "gender": "L", "marital_status": "TK",
                   "password": "Password123!"}
        r = requests.post(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30, json=payload)
        assert r.status_code in (200, 201), r.text
        emp = r.json()
        try:
            assert emp.get("overtime_hourly_rate", 0) == 0, emp
            # Verify via list
            g = requests.get(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30)
            assert g.status_code == 200
            found = next((e for e in g.json() if e["id"] == emp["id"]), None)
            assert found is not None and found.get("overtime_hourly_rate", 0) == 0
        finally:
            requests.delete(f"{API}/hr/employees/{emp['id']}", headers=_h(hrd_tok), timeout=30)
            mdb.users.delete_many({"email": "test.otr1@rumatku.id"})

    def test_budi_rate_50000(self, hrd_tok):
        emps = requests.get(f"{API}/hr/employees", headers=_h(hrd_tok), timeout=30).json()
        budi = next(e for e in emps if e["nik"] == "EMP-001")
        assert budi["overtime_hourly_rate"] == 50000
