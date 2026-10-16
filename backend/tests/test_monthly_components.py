"""ROSY monthly components on the slip (user 10 Oct 2026): build_slip takes Transport Homecare, Bonus and Potongan Tidak
Mencapai Target from the period's synced ROSY components, never from what the review page sends. Runs against a
throwaway MongoDB database that is dropped afterwards (skipped when MongoDB is not running)."""
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
EMP = {"id": "e1", "payroll_status": "active", "basic_salary": 4500000, "position_allowance": 500000,
       "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0, "ptkp_status": "TK/0"}
PERIOD = {"id": "p1", "start_date": "2026-09-01", "end_date": "2026-09-30"}


def test_build_slip_takes_bonus_and_target_deduction_from_rosy(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    import pipeline

    name = f"rasa_test_komp_{uuid.uuid4().hex[:8]}"

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(pipeline, "db", tdb)
        try:
            await tdb.period_components.insert_many([
                {"payroll_period_id": "p1", "employee_id": "e1", "kode": "TRANSPORT_HOMECARE", "nominal": 1350000.0},
                {"payroll_period_id": "p1", "employee_id": "e1", "kode": "BONUS", "nominal": 3184400.0},
                {"payroll_period_id": "p1", "employee_id": "e1", "kode": "TARGET_DEDUCTION", "nominal": 500000.0},
                {"payroll_period_id": "p1", "employee_id": "e1", "kode": "THR", "nominal": 4500000.0},
                {"payroll_period_id": "p1", "employee_id": "e1", "kode": "LOAN_INSTALLMENT", "nominal": 350000.0},
                {"payroll_period_id": "p0", "employee_id": "e1", "kode": "BONUS", "nominal": 999.0}])  # other month

            slip = await pipeline.build_slip(PERIOD, EMP, {"additional_bonus": 777777, "target_deduction": 1,
                                                           "thr": 1, "loan_installment": 1}, CFG)
            assert (slip["transport_homecare"], slip["additional_bonus"], slip["target_deduction"],
                    slip["thr"], slip["loan_installment"]) == (1350000, 3184400, 500000, 4500000, 350000)
            assert slip["position_allowance_label"] == "Tunjangan Jabatan"

            # nothing synced for the period yet: zero, never the value the review page sent
            empty = await pipeline.build_slip({**PERIOD, "id": "p9"}, EMP, {"additional_bonus": 777777, "thr": 5}, CFG)
            assert (empty["transport_homecare"], empty["additional_bonus"], empty["target_deduction"],
                    empty["thr"], empty["loan_installment"]) == (0, 0, 0, 0, 0)

            # only a PJUnit reads Bonus Threshold, not the whole Pelayanan department (user 14 Okt 2026): a Manajer
            # Pelayanan keeps "Tunjangan Jabatan" and the potongan stays a potongan
            manajer = await pipeline.build_slip(
                PERIOD, {**EMP, "department": "Pelayanan", "position": "Manajer Pelayanan"}, {}, CFG)
            assert manajer["position_allowance_label"] == "Tunjangan Jabatan"
            assert (manajer["target_from_bonus"], manajer["target_deduction"]) == (0, 500000)

            # PJUnit (13 Okt): the same ROSY potongan comes off their Bonus Threshold instead; the label is stored on
            # the slip, so review page & PDF agree
            pjunit = await pipeline.build_slip(
                PERIOD, {**EMP, "department": "Pelayanan", "position": "Penanggung Jawab unit"}, {}, CFG)
            assert pjunit["position_allowance_label"] == "Bonus Threshold"
            assert (pjunit["position_allowance"], pjunit["target_from_bonus"], pjunit["target_deduction"]) == \
                (0, 500000, 0)
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
