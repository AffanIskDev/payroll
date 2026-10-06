"""Tests for GET /api/hr/shift-recap (iteration 6).

Covers:
- Auth guard (employee token -> 403, missing/invalid month -> 400)
- March 2026 seed: EMP-001 Budi KANTOR_PUSAT REG 15, worked_on_off_day 3,
  total_worked 18, scheduled_off 2, leave 0, no_log 11; sum == days_in_month.
- Multi-shift April 2026 scenario with Siti EMP-002 on UNIT_2SHIFT: counts of
  S1 / S2, worked_on_off_day on Sunday, 1 leave; shift_codes contains REG,S1,S2.
"""
import os
from datetime import date, timedelta

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}
EMP = {"identifier": "EMP-001", "password": "Password123!"}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{API}/auth/login", json=HRD, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def emp_tok():
    r = requests.post(f"{API}/auth/login", json=EMP, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def emps(tok):
    r = requests.get(f"{API}/hr/employees", headers=_h(tok), timeout=30)
    return {e["nik"]: e for e in r.json()}


# ---- auth / validation ----

def test_shift_recap_requires_hr(emp_tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(emp_tok),
                     params={"month": "2026-03"}, timeout=30)
    assert r.status_code == 403, r.text


def test_shift_recap_bad_month(tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok),
                     params={"month": "notamonth"}, timeout=30)
    assert r.status_code == 400


def test_shift_recap_missing_month(tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok), timeout=30)
    assert r.status_code == 422


# ---- March 2026 seed verification ----

def test_shift_recap_march_structure(tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok),
                     params={"month": "2026-03"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["month"] == "2026-03"
    assert d["days_in_month"] == 31
    assert "REG" in d["shift_codes"]
    assert d["shift_names"].get("REG")
    assert isinstance(d["rows"], list) and len(d["rows"]) >= 1


def test_shift_recap_march_budi_counts(tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok),
                     params={"month": "2026-03"}, timeout=30)
    rows = {row["nik"]: row for row in r.json()["rows"]}
    budi = rows["EMP-001"]
    assert budi["schedule_code"] == "KANTOR_PUSAT"
    assert budi["shifts"].get("REG") == 15
    assert budi["worked_on_off_day"] == 3
    assert budi["total_worked"] == 18
    assert budi["scheduled_off"] == 2
    assert budi["leave"] == 0
    assert budi["no_log"] == 11


def test_shift_recap_categories_sum_to_days(tok):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok),
                     params={"month": "2026-03"}, timeout=30)
    d = r.json()
    for row in d["rows"]:
        total = sum(row["shifts"].values()) + row["worked_on_off_day"] + \
                row["scheduled_off"] + row["leave"] + row["no_log"]
        assert total == d["days_in_month"], f"{row['nik']} sum={total}"


# ---- April 2026 multi-shift scenario with Siti ----

@pytest.fixture(scope="module")
def april_scenario(tok, emps):
    """Switch Siti to UNIT_2SHIFT, insert attendance for April 2026, cleanup after."""
    siti = emps["EMP-002"]
    original = siti.copy()
    body = {k: v for k, v in original.items() if k not in ("id", "created_at", "updated_at", "_id")}
    body["work_schedule_code"] = "UNIT_2SHIFT"
    r = requests.put(f"{API}/hr/employees/{original['id']}", headers=_h(tok),
                     json=body, timeout=30)
    assert r.status_code == 200, r.text

    created = []
    # S1 days: Mon 2026-04-06 (07-15 schedule), Tue 2026-04-07
    # S2 day: Wed 2026-04-08 (13-21)
    # Leave: Thu 2026-04-09 annual_leave
    # Sunday work (off day): Sun 2026-04-05 any shift
    plan = [
        ("2026-04-05", {"check_in": "08:00", "check_out": "15:00"}),  # Sun -> worked_on_off_day
        ("2026-04-06", {"check_in": "07:00", "check_out": "15:05", "shift_code": "S1"}),
        ("2026-04-07", {"check_in": "07:00", "check_out": "15:05", "shift_code": "S1"}),
        ("2026-04-08", {"check_in": "13:00", "check_out": "21:00", "shift_code": "S2"}),
        ("2026-04-09", {"leave_type": "annual_leave", "notes": "test"}),
    ]
    for d_str, extra in plan:
        payload = {"employee_id": original["id"], "work_date": d_str, **extra}
        rr = requests.post(f"{API}/hr/attendance", headers=_h(tok), json=payload, timeout=30)
        assert rr.status_code in (200, 201), f"{d_str} -> {rr.status_code} {rr.text}"
        created.append(d_str)

    yield original

    # cleanup logs — fetch IDs then delete by id
    lr = requests.get(f"{API}/hr/attendance", headers=_h(tok),
                      params={"employee_id": original["id"],
                              "start": "2026-04-01", "end": "2026-04-30"},
                      timeout=30)
    for log in lr.json() if lr.status_code == 200 else []:
        if log["work_date"] in created:
            requests.delete(f"{API}/hr/attendance/{log['id']}",
                            headers=_h(tok), timeout=30)
    # restore schedule
    body["work_schedule_code"] = original.get("work_schedule_code", "KANTOR_PUSAT")
    requests.put(f"{API}/hr/employees/{original['id']}", headers=_h(tok),
                 json=body, timeout=30)


def test_shift_recap_april_multishift(tok, april_scenario):
    r = requests.get(f"{API}/hr/shift-recap", headers=_h(tok),
                     params={"month": "2026-04"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["days_in_month"] == 30
    # shift_codes should include REG (from Budi/Dimas) and S1/S2 (from Siti UNIT_2SHIFT)
    for c in ("REG", "S1", "S2"):
        assert c in d["shift_codes"], f"missing {c} in {d['shift_codes']}"

    rows = {r["nik"]: r for r in d["rows"]}
    siti = rows["EMP-002"]
    assert siti["schedule_code"] == "UNIT_2SHIFT"
    assert siti["shifts"].get("S1", 0) >= 2
    assert siti["shifts"].get("S2", 0) >= 1
    assert siti["worked_on_off_day"] >= 1
    assert siti["leave"] == 1
    # total_worked = shifts sum + worked_on_off_day
    assert siti["total_worked"] == sum(siti["shifts"].values()) + siti["worked_on_off_day"]
    # category sum
    total = sum(siti["shifts"].values()) + siti["worked_on_off_day"] + \
            siti["scheduled_off"] + siti["leave"] + siti["no_log"]
    assert total == 30
