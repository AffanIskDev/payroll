"""Dashboard "Perlu Ditinjau" (GET /api/hr/dashboard/employees, user request 10 Oct 2026): who joined, who left, who is
not paid or not in full, and employee data to check. 13 Oct 2026: no attendance group any more; "Tidak ikut digaji"
lists unpaid + maternity leave (not the employees without a Kontrak Gaji), and the cards count those and the employees
whose data is incomplete. Runs against a throwaway MongoDB database that is dropped afterwards (skipped when MongoDB is
not running)."""
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402


def _emp(eid, name, **kw):
    return {"id": eid, "rosy_employee_id": f"USRD-{eid}", "nik": f"N{eid}", "name": name, "payroll_status": "active",
            "join_date": "2024-01-01", "exit_date": None, "data_issues": [], **kw}


def _slip(eid, **kw):
    return {"id": f"s-{eid}", "payroll_period_id": "sep", "employee_id": eid, "status": "draft", "payroll_status": "active",
            "absence_points": 0, "take_home_pay": 1000, "pph21_amount": 10, "iuran_bpjs_kes_total": 5,
            "iuran_bpjs_tk_total": 7, **kw}


def test_dashboard_groups_who_needs_a_look(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    import pipeline
    import routes_hr

    name = f"rasa_test_dash_{uuid.uuid4().hex[:8]}"

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(routes_hr, "db", tdb)
        monkeypatch.setattr(pipeline, "db", tdb)  # get_period
        try:
            await tdb.employees.insert_many([
                _emp("a", "Ani Lama"), _emp("b", "Budi Baru", join_date="2026-09-01"),
                _emp("c", "Cici Tengah", join_date="2026-09-15"), _emp("d", "Dodi Keluar", exit_date="2026-09-20"),
                _emp("e", "Eka Unpaid", payroll_status="unpaid_leave"), _emp("f", "Fajar Alfa", data_issues=["npwp_kosong", "rekening_kosong"]),
                # incomplete data but not in September: must not be counted
                _emp("g", "Gita Agustus", data_issues=["rekening_kosong"])])
            await tdb.payroll_periods.insert_many([
                {"id": "agu", "period_name": "Agustus 2026", "start_date": "2026-08-01", "end_date": "2026-08-31",
                 "status": "approved", "employee_ids": ["a", "d", "e", "f", "g"]},
                {"id": "sep", "period_name": "September 2026", "start_date": "2026-09-01", "end_date": "2026-09-30",
                 "status": "draft", "employee_ids": ["a", "b", "c", "d", "e", "f"],
                 "employees_skipped": [{"employee_id": "USRD-x", "nik": "Nx", "name": "Xena Tanpa Kontrak",
                                        "alasan": "belum punya Kontrak Gaji"}],
                 "attendance_missing": [{"employee_id": "a", "nik": "Na", "name": "Ani Lama"}],
                 "attendance_unlinked": [{"employee_id": "USRD-b", "name": "Budi Baru"}]}])
            await tdb.attendance_daily_logs.insert_many([
                {"employee_id": "b", "work_date": d, "leave_type": "present"} for d in ("2026-09-29", "2026-09-30")])
            await tdb.payslips.insert_many([
                _slip("a", overtime_pay=50000, overtime_hours=2, transport_homecare=120000),
                _slip("b", discipline={"presence_by_type": {"maternity_leave": 3}}), _slip("c"), _slip("d"),
                # unpaid wins over maternity leave, as on the period page: counted once, as unpaid
                _slip("e", payroll_status="unpaid_leave", take_home_pay=0,
                      discipline={"presence_by_type": {"maternity_leave": 2}}),
                _slip("f", absence_points=2, absent_deduction_amount=150000, status="approved",
                      discipline={"absence_by_type": {"alpha": 1, "permission_leave": 1}})])

            r = await routes_hr.dashboard_employees()  # latest period by default
            assert r["period"]["id"] == "sep"
            g = {x["key"]: {i["name"]: i["note"] for i in x["items"]} for x in r["groups"]}
            assert g["left"] == {"Dodi Keluar": "keluar 20 September 2026",
                                 "Gita Agustus": "tidak lagi dikirim ROSY — ada di Agustus 2026, tidak ada di periode ini"}
            assert g["new"] == {"Budi Baru": "mulai 1 September 2026", "Cici Tengah": "mulai 15 September 2026"}
            # not paid because of leave (user 13 Oct 2026): unpaid and maternity leave, one row per person
            assert g["not_paid"] == {"Eka Unpaid": "cuti di luar tanggungan — upah & tunjangan Rp 0",
                                     "Budi Baru": "cuti melahirkan 3 hari — Tunj. Kehadiran terpotong"}
            # prorata only, not the alfa/izin fines (user 10 Oct 2026); the unpaid have their own group
            assert g["partial"] == {"Cici Tengah": "masuk 15 September 2026, di tengah periode — cek prorata",
                                    "Dodi Keluar": "keluar 20 September 2026, di tengah periode — cek prorata",
                                    "Budi Baru": "cuti melahirkan 3 hari, masuk kerja 2 hari — cek prorata"}
            # alfa/izin and missing attendance are not listed here any more (user 13 Oct 2026), nor counted
            assert [x["key"] for x in r["groups"]] == ["left", "new", "not_paid", "partial", "data"]
            names = {i["name"] for x in r["groups"] if x["key"] != "data" for i in x["items"]}
            assert "Fajar Alfa" not in names
            # nor is anyone without a Kontrak Gaji (Xena, HAM meta.dilewati): ROSY will not allow that any more
            assert "Xena Tanpa Kontrak" not in {i["name"] for x in r["groups"] for i in x["items"]}
            # data group = people in the period with something missing; Fajar has two gaps but is one employee
            assert [i["issues"] for x in r["groups"] if x["key"] == "data" for i in x["items"]] == \
                [["npwp_kosong", "rekening_kosong"]]
            assert r["counts"] == {"in_period": 6, "new": 2, "left": 2, "unpaid": 1, "maternity": 1, "data": 1}
            assert len(g["not_paid"]) == r["counts"]["unpaid"] + r["counts"]["maternity"]  # card = group
            assert r["payroll"] == {"slips": 6, "approved": 1, "total_thp": 5000, "total_pph21": 60,
                                    "total_bpjs_kes": 30, "total_bpjs_tk": 42}
            links = {i["name"]: i["has_slip"] for x in r["groups"] for i in x["items"]}
            assert links["Budi Baru"] and links["Eka Unpaid"] and not links["Gita Agustus"]  # Gita is not in the period

            # the period page's summary cards filter the table by employee id (user 10 Oct 2026)
            sm = (await routes_hr.period_detail("sep"))["summary"]
            assert (sm["included"], sm["overtime_hours"], sm["overtime_pay"], sm["homecare_total"]) == (6, 2, 50000, 120000)
            assert "skipped" not in sm  # the "Tidak Ikut" card (no Kontrak Gaji) is gone from the period page (user 13 Oct 2026)
            assert {k: sorted(sm[k]) for k in ("overtime", "homecare", "unpaid", "maternity", "partial")} == {
                "overtime": ["a"], "homecare": ["a"], "unpaid": ["e"], "maternity": ["b"],
                "partial": ["b", "c", "d"]}  # maternity ends mid-period, joins mid-period, leaves mid-period
            # the dashboard card counts the same people as the period page's Unpaid + Cuti Melahirkan cards
            assert (r["counts"]["unpaid"], r["counts"]["maternity"]) == (len(sm["unpaid"]), len(sm["maternity"]))

            older = await routes_hr.dashboard_employees("agu")  # the first period has nothing to compare with
            assert older["period"]["id"] == "agu" and older["counts"]["left"] == 0
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
