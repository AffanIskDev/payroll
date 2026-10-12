"""THR from ROSY on the 1721-A1 (user 12 Oct 2026): angka 7 "Tantiem, bonus, gratifikasi, jasa produksi dan THR"
counts the THR of approved slips next to Bonus. Runs against a throwaway MongoDB database that is dropped afterwards
(skipped when MongoDB is not running)."""
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"id": "e1", "nik": "2016008", "name": "Contoh Karyawan", "payroll_status": "active", "basic_salary": 4500000,
       "position_allowance": 500000, "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0,
       "ptkp_status": "TK/0"}


def test_thr_counts_in_angka_7_with_bonus(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    import tax_forms
    from engine import compute_payslip

    name = f"rasa_test_thr_{uuid.uuid4().hex[:8]}"

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(tax_forms, "db", tdb)
        try:
            months = {3: {"thr": 4500000}, 4: {"additional_bonus": 1000000}, 5: {}}  # THR in March, Bonus in April
            for m, adj in months.items():
                pid = f"p{m}"
                await tdb.payroll_periods.insert_one({"id": pid, "start_date": f"2027-{m:02d}-01",
                                                      "end_date": f"2027-{m:02d}-28"})
                slip = compute_payslip(EMP, [], CFG, adj)
                await tdb.payslips.insert_one({**slip, "payroll_period_id": pid, "employee_id": "e1",
                                               "status": "approved"})
            a1 = await tax_forms.build_1721a1(EMP, 2027, 1)
            assert a1["items"]["i7"] == 4500000 + 1000000
            assert a1["items"]["i8"] == sum(a1["items"][k] for k in ("i1", "i2", "i3", "i4", "i5", "i6", "i7", "i7a"))
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
