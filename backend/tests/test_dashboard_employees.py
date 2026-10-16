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
            "join_date": "2024-01-01", "exit_date": None, "data_issues": [], "bank_code": "BSI",
            "bank_name": "Bank Syariah Indonesia", "bank_account_number": "7123456789", "bank_account_name": name, **kw}


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
                _emp("c", "Cici Tengah", join_date="2026-09-15", bank_account_name=""), _emp("d", "Dodi Keluar", exit_date="2026-09-20"),
                _emp("e", "Eka Unpaid", payroll_status="unpaid_leave"), _emp("f", "Fajar Alfa", data_issues=["npwp_kosong", "rekening_kosong"]),
                # incomplete data but not in September: must not be counted
                _emp("g", "Gita Agustus", data_issues=["rekening_kosong"]),
                # on maternity leave the whole period: paid gapok only (user 14 Oct 2026)
                _emp("h", "Hana Cuti Penuh"),
                # back from maternity leave inside the period, slip already prorated by RUSA (user 15 Oct 2026): the leave
                # days are no poin any more, so only the slip's prorata knows them
                _emp("i", "Indah Kembali")])
            await tdb.payroll_periods.insert_many([
                {"id": "agu", "period_name": "Agustus 2026", "start_date": "2026-08-01", "end_date": "2026-08-31",
                 "status": "approved", "employee_ids": ["a", "d", "e", "f", "g"]},
                {"id": "sep", "period_name": "September 2026", "start_date": "2026-09-01", "end_date": "2026-09-30",
                 "status": "draft", "employee_ids": ["a", "b", "c", "d", "e", "f", "h", "i"],
                 "employees_skipped": [{"employee_id": "USRD-x", "nik": "Nx", "name": "Xena Tanpa Kontrak",
                                        "alasan": "belum punya Kontrak Gaji"}],
                 "attendance_missing": [{"employee_id": "a", "nik": "Na", "name": "Ani Lama"}],
                 "attendance_unlinked": [{"employee_id": "USRD-b", "name": "Budi Baru"}]}])
            await tdb.attendance_daily_logs.insert_many([
                {"employee_id": eid, "work_date": d, "leave_type": "present"} for d in ("2026-09-29", "2026-09-30")
                for eid in ("b", "i")])
            await tdb.payslips.insert_many([
                _slip("a", overtime_pay=50000, overtime_hours=2, transport_homecare=120000),
                _slip("b", discipline={"presence_by_type": {"maternity_leave": 3}}), _slip("c"), _slip("d"),
                # unpaid wins over maternity leave, as on the period page: counted once, as unpaid
                _slip("e", payroll_status="unpaid_leave", take_home_pay=0,
                      discipline={"presence_by_type": {"maternity_leave": 2}}),
                _slip("f", absence_points=2, absent_deduction_amount=150000, status="approved",
                      discipline={"absence_by_type": {"alpha": 1, "permission_leave": 1}}),
                _slip("h", maternity_basic_only=True, discipline={"presence_by_type": {"maternity_leave": 20}}),
                _slip("i", discipline={"presence_by_type": {}}, prorata={
                    "kind": "cuti_melahirkan", "from": "2026-09-01", "to": "2026-09-30", "divisor": 25, "work_days": 26,
                    "maternity_days": 11, "basic_factor": 1, "attendance_days": 15, "attendance_factor": 0.6,
                    "source": "presensi"}),
                # the period before, for the arrows on the cards (user 14 Oct 2026)
                _slip("a", id="s-a-agu", payroll_period_id="agu", take_home_pay=1500, pph21_amount=20),
                _slip("d", id="s-d-agu", payroll_period_id="agu", take_home_pay=900),
                _slip("e", id="s-e-agu", payroll_period_id="agu", take_home_pay=0, payroll_status="unpaid_leave"),
                _slip("f", id="s-f-agu", payroll_period_id="agu", take_home_pay=1000),
                _slip("g", id="s-g-agu", payroll_period_id="agu", take_home_pay=1100)])

            r = await routes_hr.dashboard_employees()  # latest period by default
            assert r["period"]["id"] == "sep"
            g = {x["key"]: {i["name"]: i["note"] for i in x["items"]} for x in r["groups"]}
            assert g["left"] == {"Dodi Keluar": "keluar 20 September 2026",
                                 "Gita Agustus": "tanpa tanggal keluar di ROSY — ada di Agustus 2026, tidak ada di periode ini"}
            assert g["new"] == {"Budi Baru": "mulai 1 September 2026", "Cici Tengah": "mulai 15 September 2026"}
            # not paid = unpaid only (user 14 Oct 2026): maternity leave is paid — Budi (leave ends inside the period) and
            # Hana (the whole period, gapok only) are not "Tidak ikut digaji", whatever their slips carry
            assert g["not_paid"] == {"Eka Unpaid": "cuti di luar tanggungan — upah & tunjangan Rp 0"}
            # prorata only, not the alfa/izin fines (user 10 Oct 2026); the unpaid have their own group. A maternity leave
            # that covers the whole period pays gapok only (user 14 Oct 2026): not a full salary, so it is listed here
            assert g["partial"] == {"Cici Tengah": "masuk 15 September 2026, di tengah periode — cek prorata",
                                    "Dodi Keluar": "keluar 20 September 2026, di tengah periode — cek prorata",
                                    "Budi Baru": "cuti melahirkan 3 hari, masuk kerja 2 hari — cek prorata",
                                    "Hana Cuti Penuh": "cuti melahirkan 20 hari — dibayarkan gaji pokok saja",
                                    "Indah Kembali": "cuti melahirkan 11 hari, masuk kerja 2 hari — Tunjangan Kehadiran "
                                                     "diprorata 15/25 hari kerja"}
            # accounts that block submitting & Lock & Approve come first (user 14 Oct 2026): Cici has no Nama di Rekening; Fajar's
            # slip is already approved and Eka's unpaid Rp 0 slip transfers nothing, so neither is listed
            assert g["bank"] == {"Cici Tengah": "Nama rekening kosong — payroll belum bisa diproses"}
            # alfa/izin and missing attendance are not listed here any more (user 13 Oct 2026), nor counted
            assert [x["key"] for x in r["groups"]] == ["bank", "left", "new", "not_paid", "partial", "data"]
            names = {i["name"] for x in r["groups"] if x["key"] != "data" for i in x["items"]}
            assert "Fajar Alfa" not in names
            # nor is anyone without a Kontrak Gaji (Xena, HAM meta.dilewati): ROSY will not allow that any more
            assert "Xena Tanpa Kontrak" not in {i["name"] for x in r["groups"] for i in x["items"]}
            # data group = people in the period with something missing; Fajar has two gaps but is one employee
            assert [i["issues"] for x in r["groups"] if x["key"] == "data" for i in x["items"]] == \
                [["npwp_kosong", "rekening_kosong"]]
            assert r["counts"] == {"in_period": 8, "new": 2, "left": 2, "unpaid": 1, "data": 1}
            assert len(g["not_paid"]) == r["counts"]["unpaid"]  # card = group
            assert r["payroll"] == {"slips": 8, "approved": 1, "total_thp": 7000, "total_pph21": 80,
                                    "total_bpjs_kes": 40, "total_bpjs_tk": 56}
            # nominal cards and the headcount against the period before (user 14 Oct 2026): Agustus has 5 employees and
            # slips worth 4500 THP / 60 PPh 21 / 25 BPJS Kes / 35 BPJS TK
            assert r["compare"] == {
                "period_name": "Agustus 2026",
                "in_period": {"prev": 5, "diff": 3, "pct": 60.0},
                "total_thp": {"prev": 4500, "diff": 2500, "pct": 55.6},
                "total_pph21": {"prev": 60, "diff": 20, "pct": 33.3},
                "total_bpjs_kes": {"prev": 25, "diff": 15, "pct": 60.0},
                "total_bpjs_tk": {"prev": 35, "diff": 21, "pct": 60.0}}
            links = {i["name"]: i["has_slip"] for x in r["groups"] for i in x["items"]}
            assert links["Budi Baru"] and links["Eka Unpaid"] and not links["Gita Agustus"]  # Gita is not in the period

            # the period page's summary cards filter the table by employee id (user 10 Oct 2026)
            pd = await routes_hr.period_detail("sep")
            sm = pd["summary"]
            # the "Rekening Belum Siap" card and the banner list the same people as the dashboard group (user 14 Oct 2026)
            assert sm["bank"] == ["c"] and [(b["nik"], b["name"]) for b in pd["bank_blockers"]] == [("Nc", "Cici Tengah")]
            assert (sm["included"], sm["overtime_hours"], sm["overtime_pay"], sm["homecare_total"]) == (8, 2, 50000, 120000)
            assert "skipped" not in sm  # the "Tidak Ikut" card (no Kontrak Gaji) is gone from the period page (user 13 Oct 2026)
            assert {k: sorted(sm[k]) for k in ("overtime", "homecare", "unpaid", "maternity", "partial")} == {
                "overtime": ["a"], "homecare": ["a"], "unpaid": ["e"], "maternity": ["b", "h", "i"],
                "partial": ["b", "c", "d", "i"]}  # maternity ends mid-period, joins mid-period, leaves mid-period
            # the dashboard card counts the same people as the period page's Unpaid card (maternity leave is paid)
            assert r["counts"]["unpaid"] == len(sm["unpaid"])

            older = await routes_hr.dashboard_employees("agu")  # the first period has nothing to compare with
            assert older["period"]["id"] == "agu" and older["counts"]["left"] == 0 and older["compare"] is None
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_prorated_slips_say_by_how_much():
    """Since 15 Oct 2026 RUSA prorates joining, leaving and maternity leave inside the period (engine.prorata): the
    "Gaji tidak penuh" note says by how much instead of "cek prorata"; a slip of 25 working days or more is not listed."""
    import routes_hr

    sep = {"start_date": "2026-09-01", "end_date": "2026-09-30"}

    def pr(**kw):
        return {"prorata": {"kind": "masuk", "from": "2026-09-14", "to": "2026-09-30", "divisor": 25, "work_days": 15,
                            "maternity_days": 0, "basic_factor": 0.6, "attendance_days": 15, "attendance_factor": 0.6,
                            "source": "presensi", **kw}}

    note = routes_hr._prorata_note
    assert note(pr(), {"join_date": "2026-09-14"}, sep, 0, 15) == \
        "masuk 14 September 2026, di tengah periode — gaji diprorata 15/25 hari kerja"
    assert note(pr(kind="keluar", work_days=5, basic_factor=0.2, attendance_days=5, attendance_factor=0.2),
                {"exit_date": "2026-09-07"}, sep, 0, 5) == "keluar 7 September 2026, di tengah periode — gaji diprorata 5/25 hari kerja"
    assert note(pr(kind="masuk_keluar", work_days=6, basic_factor=0.24), {"join_date": "2026-09-14", "exit_date": "2026-09-19"},
                sep, 0, 6) == "masuk 14 September 2026, keluar 19 September 2026, di tengah periode — gaji diprorata 6/25 hari kerja"
    assert note(pr(work_days=25, basic_factor=1, attendance_days=25, attendance_factor=1), {"join_date": "2026-09-02"},
                sep, 0, 25) is None                                            # a full month after all
    assert note({}, {"join_date": "2026-09-14"}, sep, 0, 15) == \
        "masuk 14 September 2026, di tengah periode — cek prorata"             # calculated before 15 Oct: not prorated yet


@pytest.mark.parametrize("now,before,expected", [
    (110, 100, {"prev": 100, "diff": 10, "pct": 10.0}),                       # up
    (90, 100, {"prev": 100, "diff": -10, "pct": -10.0}),                      # down
    (100, 100, {"prev": 100, "diff": 0, "pct": 0.0}),                         # same
    (214, 212, {"prev": 212, "diff": 2, "pct": 0.9}),                         # headcount, one decimal
    (1548293785, 1545922583, {"prev": 1545922583, "diff": 2371202, "pct": 0.2}),
    (1000, 0, {"prev": 0, "diff": 1000, "pct": None}),                        # nothing before: no arrow, no division by 0
    (0, 0, {"prev": 0, "diff": 0, "pct": None}),
])
def test_delta_against_the_period_before(now, before, expected):
    import routes_hr
    assert routes_hr._delta(now, before) == expected
