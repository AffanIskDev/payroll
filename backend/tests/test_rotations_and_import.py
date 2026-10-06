"""Tests for shift rotations and Rumatku attendance import (iteration 5).

Covers:
- GET /api/hr/shift-rotations (week normalization, filter employees to multi-shift)
- PUT /api/hr/shift-rotations (upsert, delete via null, invalid shift -> 400)
- Shift priority: manual > rotation > auto (nearest check-in)
- POST /api/hr/attendance/import (template, formats, skip/update/error rules)
"""
import io
import os
from datetime import date

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "https://hr-automation-65.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
HRD = {"identifier": "hrd.manager@rumatku.id", "password": "Password123!"}

APR_MON = "2026-04-06"   # Mon week 1
APR_W2 = "2026-04-13"    # Mon week 2
APR_W3 = "2026-04-20"
APR_W4 = "2026-04-27"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{API}/auth/login", json=HRD, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def emps(tok):
    r = requests.get(f"{API}/hr/employees", headers=_h(tok), timeout=30)
    return {e["nik"]: e for e in r.json()}


@pytest.fixture(scope="module")
def siti_u2shift(tok, emps):
    """Temporarily switch Siti (EMP-002) to UNIT_2SHIFT, restore after module."""
    original = emps["EMP-002"].copy()
    body = {k: v for k, v in original.items() if k not in ("id", "created_at", "updated_at", "_id")}
    body["work_schedule_code"] = "UNIT_2SHIFT"
    r = requests.put(f"{API}/hr/employees/{original['id']}", headers=_h(tok), json=body, timeout=30)
    assert r.status_code == 200, r.text
    yield r.json()
    # restore
    body["work_schedule_code"] = original.get("work_schedule_code", "KANTOR_PUSAT")
    requests.put(f"{API}/hr/employees/{original['id']}", headers=_h(tok), json=body, timeout=30)
    # cleanup rotations
    requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
        "assignments": [{"employee_id": original["id"], "week_start": w, "shift_code": None}
                        for w in (APR_MON, APR_W2, APR_W3, APR_W4)]})


def _del_log(tok, eid, wd):
    """Delete an attendance log by employee_id + work_date."""
    logs = requests.get(f"{API}/hr/attendance", headers=_h(tok), timeout=30,
                        params={"employee_id": eid, "start": wd, "end": wd}).json()
    for log in logs:
        requests.delete(f"{API}/hr/attendance/{log['id']}", headers=_h(tok), timeout=30)


# --------------------- GET / PUT /shift-rotations ---------------------
class TestRotationsCRUD:
    def test_week_normalization_and_4weeks(self, tok, siti_u2shift):
        # Pass a Wednesday — must normalize to Mon 2026-04-06
        r = requests.get(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30,
                         params={"start": "2026-04-08", "weeks": 4})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["weeks"] == [APR_MON, APR_W2, APR_W3, APR_W4]

    def test_only_multishift_employees_listed(self, tok, siti_u2shift, emps):
        d = requests.get(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30,
                        params={"start": APR_MON, "weeks": 4}).json()
        niks = {e["nik"] for e in d["employees"]}
        assert "EMP-002" in niks  # Siti is now UNIT_2SHIFT
        assert "EMP-001" not in niks  # Budi is KANTOR_PUSAT (single shift)
        siti = [e for e in d["employees"] if e["nik"] == "EMP-002"][0]
        codes = {s["code"] for s in siti["shifts"]}
        assert codes == {"S1", "S2"}

    def test_put_upsert_and_delete_via_null(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        # upsert
        r = requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": "S2"}]})
        assert r.status_code == 200
        assert r.json()["saved"] == 1
        d = requests.get(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30,
                        params={"start": APR_MON, "weeks": 4}).json()
        assert any(a["employee_id"] == eid and a["week_start"] == APR_MON and a["shift_code"] == "S2"
                   for a in d["assignments"])
        # delete via null
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": None}]})
        d2 = requests.get(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30,
                         params={"start": APR_MON, "weeks": 4}).json()
        assert not any(a["employee_id"] == eid and a["week_start"] == APR_MON for a in d2["assignments"])

    def test_put_invalid_shift_code_400(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        r = requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": "BOGUS"}]})
        assert r.status_code == 400

    def test_week_start_normalizes_on_put(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        # Send a Wed; backend should normalize to Mon when storing
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": "2026-04-15", "shift_code": "S1"}]})
        d = requests.get(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30,
                        params={"start": APR_MON, "weeks": 4}).json()
        assert any(a["week_start"] == APR_W2 and a["shift_code"] == "S1" for a in d["assignments"]
                   if a["employee_id"] == eid)
        # cleanup
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_W2, "shift_code": None}]})


# --------------------- Shift priority ---------------------
class TestShiftPriority:
    def _post(self, tok, body):
        return requests.post(f"{API}/hr/attendance", headers=_h(tok), timeout=30, json=body)

    def test_rotation_overrides_nearest(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        # set rotation S2 for week APR_MON
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": "S2"}]})
        r = self._post(tok, {"employee_id": eid, "work_date": APR_MON,
                             "check_in_time": "07:30", "check_out_time": "15:00",
                             "leave_type": "present"})
        assert r.status_code == 200, r.text
        log = r.json()
        assert log["shift_code"] == "S2"
        assert log["shift_source"] == "rotation"
        assert log["schedule_start"] == "13:00" and log["schedule_end"] == "21:00"
        assert log["minutes_late"] == 0        # check_in 07:30 before start 13:00
        assert log["minutes_early_leave"] == 360  # 21:00 - 15:00
        _del_log(tok, eid, APR_MON)
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": None}]})

    def test_auto_nearest_without_rotation(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        r = self._post(tok, {"employee_id": eid, "work_date": APR_MON,
                             "check_in_time": "07:30", "check_out_time": "15:00",
                             "leave_type": "present"})
        log = r.json()
        assert log["shift_code"] == "S1"
        assert log["shift_source"] == "auto"
        assert log["minutes_late"] == 30
        assert log["minutes_early_leave"] == 0
        _del_log(tok, eid, APR_MON)

    def test_manual_overrides_rotation(self, tok, siti_u2shift, emps):
        eid = emps["EMP-002"]["id"]
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": "S2"}]})
        r = self._post(tok, {"employee_id": eid, "work_date": APR_MON,
                             "check_in_time": "07:30", "check_out_time": "15:00",
                             "shift_code": "S1", "leave_type": "present"})
        log = r.json()
        assert log["shift_code"] == "S1"
        assert log["shift_source"] == "manual"
        _del_log(tok, eid, APR_MON)
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": eid, "week_start": APR_MON, "shift_code": None}]})


# --------------------- Rumatku import ---------------------
class TestImport:
    def test_template_download(self, tok):
        r = requests.get(f"{API}/hr/attendance/import-template", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        body = r.content.decode()
        header = body.splitlines()[0].split(",")
        for col in ["nik", "tanggal", "jam_masuk", "jam_pulang", "foto_masuk",
                    "foto_pulang", "lokasi_masuk", "lokasi_pulang", "keterangan"]:
            assert col in header, header

    def test_import_mixed_rows(self, tok, siti_u2shift, emps):
        bid = emps["EMP-001"]["id"]
        sid = emps["EMP-002"]["id"]
        # set rotation S2 week 2026-04-13 for Siti → import date 2026-04-14 Tue
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": sid, "week_start": APR_W2, "shift_code": "S2"}]})
        # Pre-cleanup any leftover logs on these dates from prior runs
        for wd in ("2026-04-07", "2026-04-12", "2026-04-14", "2026-04-15"):
            _del_log(tok, bid, wd)
            _del_log(tok, sid, wd)
        # Pre-create a non-present log that should be SKIPPED
        requests.post(f"{API}/hr/attendance", headers=_h(tok), timeout=30, json={
            "employee_id": bid, "work_date": "2026-04-15", "leave_type": "annual_leave"})

        csv_body = (
            "nik,tanggal,jam_masuk,jam_pulang,foto_masuk,foto_pulang,lokasi_masuk,lokasi_pulang,keterangan\n"
            # Budi normal, DD/MM/YYYY + dot-time formats
            'EMP-001,07/04/2026,08.05,16.00,http://ex/f1.jpg,http://ex/f2.jpg,"-6.26,107.15","-6.26,107.16",\n'
            # Siti with rotation S2 → should import as S2
            "EMP-002,2026-04-14,07:30,15:00,,,,,\n"
            # Budi Sunday on KANTOR_PUSAT → LIBUR
            "EMP-001,2026-04-12,08:00,16:00,,,,,\n"
            # Unknown NIK
            "BOGUS-99,2026-04-07,08:00,16:00,,,,,\n"
            # Missing both times
            "EMP-001,2026-04-08,,,,,,,\n"
            # Pre-existing non-present → skipped
            "EMP-001,2026-04-15,08:05,16:00,,,,,\n"
        )
        files = {"file": ("rumatku.csv", io.BytesIO(csv_body.encode()), "text/csv")}
        r = requests.post(f"{API}/hr/attendance/import", headers=_h(tok), files=files, timeout=60)
        assert r.status_code == 200, r.text
        res = r.json()
        # expect 3 created (Budi 2026-04-07, Siti 2026-04-14, Budi 2026-04-12)
        assert res["created"] == 3, res
        assert len(res["errors"]) == 2, res["errors"]       # unknown NIK + missing times
        assert len(res["skipped"]) == 1, res["skipped"]     # existing annual_leave
        assert res["shift_summary"].get("S2", 0) >= 1
        assert res["shift_summary"].get("LIBUR", 0) >= 1

        # Verify Siti imported log has rotation shift
        siti_logs = requests.get(f"{API}/hr/attendance", headers=_h(tok), timeout=30,
                                 params={"employee_id": sid, "start": "2026-04-14",
                                         "end": "2026-04-14"}).json()
        assert siti_logs[0]["shift_code"] == "S2"
        assert siti_logs[0]["shift_source"] == "rotation"
        assert siti_logs[0]["source"] == "rumatku_import"
        assert siti_logs[0]["photo_in_url"] in (None, "", None)  # empty in csv

        # Verify Budi Sunday on KANTOR_PUSAT = LIBUR (is_off_day True, 0/0)
        budi_sun = requests.get(f"{API}/hr/attendance", headers=_h(tok), timeout=30,
                                params={"employee_id": bid, "start": "2026-04-12",
                                        "end": "2026-04-12"}).json()[0]
        assert budi_sun["is_off_day"] is True
        assert budi_sun["minutes_late"] == 0 and budi_sun["minutes_early_leave"] == 0

        # Re-import same Budi 2026-04-07 row → should UPDATE
        csv2 = ("nik,tanggal,jam_masuk,jam_pulang,foto_masuk,foto_pulang,lokasi_masuk,lokasi_pulang,keterangan\n"
                "EMP-001,2026-04-07,08:10,16:00,,,,,re-import\n")
        files2 = {"file": ("r2.csv", io.BytesIO(csv2.encode()), "text/csv")}
        r2 = requests.post(f"{API}/hr/attendance/import", headers=_h(tok), files=files2, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["updated"] == 1 and r2.json()["created"] == 0

        # cleanup created logs
        for wd in ("2026-04-07", "2026-04-12", "2026-04-14"):
            _del_log(tok, bid, wd)
            _del_log(tok, sid, wd)
        _del_log(tok, bid, "2026-04-15")   # the annual_leave seed
        requests.put(f"{API}/hr/shift-rotations", headers=_h(tok), timeout=30, json={
            "assignments": [{"employee_id": sid, "week_start": APR_W2, "shift_code": None}]})


# --------------------- Regression ---------------------
class TestRegression:
    def test_maret_2026_budi_unchanged(self, tok, emps):
        periods = requests.get(f"{API}/hr/periods", headers=_h(tok), timeout=30).json()
        pid = next((p["id"] for p in periods if p["period_name"] == "Maret 2026"), None)
        if not pid:
            pytest.skip("Maret 2026 not seeded")
        r = requests.get(f"{API}/hr/periods/{pid}/employees/{emps['EMP-001']['id']}",
                         headers=_h(tok), timeout=30).json()
        s = r["payslip"]
        assert s["discipline"]["total_points"] == 4
        assert s["late_penalty_amount"] == 160000
