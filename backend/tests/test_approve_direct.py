"""Lock & Approve straight from draft (user decision 10 Oct 2026): the Manager no longer waits for the Supervisor to
submit. Runs the endpoints against a throwaway MongoDB database that is dropped afterwards (skipped when MongoDB is
not running); the encrypted PDF and the Rumatku delivery are stubbed, so nothing is written or sent."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

MANAGER = {"id": "u1", "username": "melia", "name": "Meliawasni", "role": "manager_hrd"}


def _period(pid, **kw):
    return {"id": pid, "period_name": "September 2026", "start_date": "2026-09-01", "end_date": "2026-09-30",
            "status": "draft", "attendance_synced_at": "2026-10-10T03:01:34+00:00", **kw}


def _slip(pid, eid):
    return {"id": f"{pid}-{eid}", "payroll_period_id": pid, "employee_id": eid, "status": "draft",
            "take_home_pay": 1000, "employee": {"nik": eid, "name": eid, "birth_date": "1995-01-01"}}


def test_manager_locks_and_approves_straight_from_draft(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    import pipeline
    import routes_hr

    name = f"rasa_test_appr_{uuid.uuid4().hex[:8]}"
    pdfs, deliveries = [], []

    async def fake_queue(pid, *a, **kw):
        deliveries.append(pid)
        return 0

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(routes_hr, "db", tdb)
        monkeypatch.setattr(pipeline, "db", tdb)
        def fake_pdf(slip, period):
            if slip["id"].startswith("boom"):
                raise RuntimeError("cryptography>=3.1 is required for AES algorithm")  # seen on 10 Oct 2026
            pdfs.append(slip["id"])
            return "/dev/null"

        monkeypatch.setattr(pipeline, "save_encrypted", fake_pdf)
        monkeypatch.setattr(pipeline, "queue_delivery", fake_queue)
        status = lambda pid: tdb.payroll_periods.find_one({"id": pid}, {"_id": 0, "status": 1})  # noqa: E731
        try:
            now = datetime.now(timezone.utc).isoformat()
            await tdb.payroll_periods.insert_many([
                _period("ok"), _period("unsynced", attendance_synced_at=None), _period("syncing", sync_running_since=now),
                _period("locked", status="approved"), _period("empty"), _period("one"), _period("boom")])
            await tdb.payslips.insert_many([_slip("ok", "a"), _slip("ok", "b"), _slip("unsynced", "a"),
                                            _slip("syncing", "a"), _slip("one", "a"), _slip("one", "b"),
                                            _slip("boom", "a")])

            # draft, synced: every slip locked, period approved, slips queued for Rumatku once
            assert await routes_hr.approve_all("ok", MANAGER) == {"approved": 2}
            assert (await status("ok"))["status"] == "approved"
            assert await tdb.payslips.count_documents({"payroll_period_id": "ok", "status": "approved"}) == 2
            assert sorted(pdfs) == ["ok-a", "ok-b"] and deliveries == ["ok"]
            history = (await tdb.payroll_periods.find_one({"id": "ok"}))["review_history"]
            assert [h["action"] for h in history] == ["approved"] and history[0]["by_name"] == "Meliawasni"

            # the gates submitting had still hold, and a refused period stays editable
            for pid, code, text in (("unsynced", 400, "Sinkron dari ROSY belum berhasil"),
                                    ("syncing", 409, "sedang disinkron"), ("locked", 400, "sudah dikunci"),
                                    ("empty", 400, "Belum ada slip")):
                with pytest.raises(HTTPException) as e:
                    await routes_hr.approve_all(pid, MANAGER)
                assert e.value.status_code == code and text in e.value.detail, (pid, e.value.detail)
                assert (await status(pid))["status"] == ("approved" if pid == "locked" else "draft")

            # the PDF fails before anything is locked: the draft is given back, not left waiting for approval
            with pytest.raises(RuntimeError):
                await routes_hr.approve_all("boom", MANAGER)
            assert (await status("boom"))["status"] == "draft"

            # one slip from the review page, straight from draft; the rest of the period is untouched
            await routes_hr.approve_one("one", "a", MANAGER)
            assert (await tdb.payslips.find_one({"id": "one-a"}))["status"] == "approved"
            assert (await tdb.payslips.find_one({"id": "one-b"}))["status"] == "draft"
            assert (await status("one"))["status"] == "draft"
            with pytest.raises(HTTPException) as e:
                await routes_hr.approve_one("unsynced", "a", MANAGER)
            assert e.value.status_code == 400
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
