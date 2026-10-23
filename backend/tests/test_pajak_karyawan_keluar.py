"""Masa pajak terakhir karyawan keluar (user 20 Okt 2026, PMK 168/2023): slip di bulan tanggal keluar dihitung Pasal 17
atas penghasilan Januari s/d bulan keluar (saldo awal YTD + slip sistem + slip bulan itu, tidak disetahunkan, PTKP
setahun penuh) dikurangi PPh 21 yang sudah dipotong — lebih bayar = negatif, kurang bayar = positif, seperti Desember.
Uji engine tanpa server; uji slip & 1721-A1 memakai MongoDB sekali pakai yang di-drop sesudahnya (dilewati bila MongoDB
lokal tidak berjalan)."""
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

from engine import annual_tax_summary, compute_payslip  # noqa: E402
from pipeline import final_tax_kind  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"id": "e1", "nik": "2024065", "name": "Uji Keluar", "payroll_status": "active", "basic_salary": 3000000,
       "position_allowance": 0, "monthly_attendance_allowance": 1000000, "overtime_hourly_rate": 0,
       "ptkp_status": "TK/0", "join_date": "2024-03-01"}
OKT = {"id": "p10", "start_date": "2026-10-01", "end_date": "2026-10-31"}


# ---------------------------------------------------------------- kapan sebuah slip menjadi masa pajak terakhir
@pytest.mark.parametrize("period,exit_date,expected", [
    (OKT, None, None),                                          # bulan biasa: TER
    (OKT, "2026-10-06", "keluar"),
    (OKT, "2026-10-01", "keluar"),                              # hari pertama & terakhir periode ikut
    (OKT, "2026-10-31", "keluar"),
    (OKT, "2026-11-02", None),                                  # keluar bulan depan: Oktober masih TER
    (OKT, "2026-09-30", None),
    ({"id": "p12", "start_date": "2026-12-01", "end_date": "2026-12-31"}, None, "desember"),
    ({"id": "p12", "start_date": "2026-12-01", "end_date": "2026-12-31"}, "2026-12-15", "desember"),
])
def test_final_tax_kind(period, exit_date, expected):
    assert final_tax_kind(period, {**EMP, "exit_date": exit_date}) == expected


def test_engine_marks_the_reconciliation_with_its_kind_and_month():
    ctx = {"tax_year": 2026, "has_initial_balance": True, "initial_months": 9, "initial_gross": 43053400.0,
           "initial_jht_jp": 0.0, "initial_pph21": 336501.0, "system_gross": 0, "system_jht_jp": 0, "system_pph21": 0,
           "system_months": 0, "kind": "keluar", "final_month": 10}
    s = compute_payslip({**EMP, "exit_date": "2026-10-06"}, [], CFG, {}, ctx, OKT)
    r = s["tax_reconciliation"]
    assert s["pph21_method"] == "pasal17" and r["kind"] == "keluar" and r["final_month"] == 10
    assert r["gross_year"] == 43053400 + s["taxable_gross"]
    assert r["annual_tax"] == 0                                  # Jan–Okt di bawah PTKP setahun
    assert s["pph21_amount"] == r["pph21_december"] == -336501   # seluruh PPh Jan–Sep dikembalikan
    # slip lama / konteks Desember tanpa kind tetap dibaca sebagai Desember
    old = {k: v for k, v in ctx.items() if k not in ("kind", "final_month")}
    r12 = compute_payslip(EMP, [], CFG, {}, old)["tax_reconciliation"]
    assert r12["kind"] == "desember" and r12["final_month"] == 12


# ---------------------------------------------------------------- MongoDB: slip bulan keluar & 1721-A1
def _with_throwaway_db(coro_fn):
    from motor.motor_asyncio import AsyncIOMotorClient

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        name = f"rasa_test_keluar_{uuid.uuid4().hex[:8]}"
        try:
            await coro_fn(client[name])
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def _slip(gross, pph, jht=60000, jp=30000):
    return {"taxable_gross": gross, "pph21_amount": pph, "bpjs": {"jht_employee": jht, "jp_employee": jp}}


async def _period(tdb, m):
    pid = f"p{m}"
    await tdb.payroll_periods.insert_one({"id": pid, "bulan": f"2026-{m:02d}", "start_date": f"2026-{m:02d}-01",
                                          "end_date": f"2026-{m:02d}-28"})
    return pid


def test_exit_month_slip_settles_the_tax_with_initial_balance(monkeypatch):
    import pipeline

    async def body(tdb):
        monkeypatch.setattr(pipeline, "db", tdb)
        await tdb.employee_tax_initial_balances.insert_one(
            {"employee_id": "e1", "tax_year": 2026, "cutoff_month": 9, "gross_income_ytd": 43053400.0,
             "employee_jht_jp_ytd": 0.0, "pph21_paid_ytd": 336501.0})
        # slip September sistem: sebelum/sama dengan cutoff → tidak dihitung lagi (sudah di saldo awal)
        await tdb.payslips.insert_one({**_slip(4800000, 46000), "employee_id": "e1",
                                       "payroll_period_id": await _period(tdb, 9)})
        await tdb.payroll_periods.insert_one({**OKT, "bulan": "2026-10"})
        s = await pipeline.build_slip(OKT, {**EMP, "exit_date": "2026-10-06"}, {}, CFG)
        r = s["tax_reconciliation"]
        assert s["pph21_method"] == "pasal17" and r["kind"] == "keluar" and r["system_months"] == 0
        assert s["prorata"]["kind"] == "keluar"                 # gaji tetap diprorata sampai tanggal keluar
        assert s["pph21_amount"] == -336501
        # karyawan yang tidak keluar di bulan yang sama tetap TER
        stay = await pipeline.build_slip(OKT, EMP, {}, CFG)
        assert stay["pph21_method"] == "ter" and stay["tax_reconciliation"] is None

    _with_throwaway_db(body)


def test_exit_month_without_initial_balance_uses_earlier_slips_only(monkeypatch):
    import pipeline

    async def body(tdb):
        monkeypatch.setattr(pipeline, "db", tdb)
        rich = {**EMP, "basic_salary": 20000000, "exit_date": "2026-10-20"}
        for m in (7, 8, 9):
            await tdb.payslips.insert_one({**_slip(21000000, 200000), "employee_id": "e1",
                                           "payroll_period_id": await _period(tdb, m)})
        # periode sesudah bulan keluar tidak boleh ikut (mis. slip November yang masih tersisa)
        await tdb.payslips.insert_one({**_slip(99000000, 9), "employee_id": "e1",
                                       "payroll_period_id": await _period(tdb, 11)})
        await tdb.payroll_periods.insert_one({**OKT, "bulan": "2026-10"})
        s = await pipeline.build_slip(OKT, rich, {}, CFG)
        r = s["tax_reconciliation"]
        assert r["system_months"] == 3 and r["system_gross"] == 63000000 and r["pph21_paid_jan_nov"] == 600000
        t = annual_tax_summary(r["gross_year"], r["jht_jp_year"], 4, "TK/0")  # 3 slip + bulan keluar
        assert r["biaya_jabatan"] == t["biaya_jabatan"] == 2000000            # maks 500 rb × 4 bulan
        assert s["pph21_amount"] == t["annual_tax"] - 600000 > 0              # kurang bayar → dipotong di slip terakhir

    _with_throwaway_db(body)


def test_1721a1_is_final_at_the_exit_month(monkeypatch):
    import tax_forms

    async def body(tdb):
        monkeypatch.setattr(tax_forms, "db", tdb)
        await tdb.employee_tax_initial_balances.insert_one(
            {"employee_id": "e1", "tax_year": 2026, "cutoff_month": 9, "gross_income_ytd": 43053400.0,
             "employee_jht_jp_ytd": 0.0, "pph21_paid_ytd": 336501.0})
        await tdb.payroll_periods.insert_one({**OKT, "bulan": "2026-10"})
        leaver = {**EMP, "exit_date": "2026-10-06"}
        ctx = {"tax_year": 2026, "has_initial_balance": True, "initial_months": 9, "initial_gross": 43053400.0,
               "initial_jht_jp": 0.0, "initial_pph21": 336501.0, "system_gross": 0, "system_jht_jp": 0,
               "system_pph21": 0, "system_months": 0, "kind": "keluar", "final_month": 10}
        slip = compute_payslip(leaver, [], CFG, {}, ctx, OKT)
        await tdb.payslips.insert_one({**slip, "payroll_period_id": "p10", "employee_id": "e1", "status": "approved"})
        a1 = await tax_forms.build_1721a1(leaver, 2026, 1)
        assert a1["masa_start"] == 1 and a1["masa_end"] == 10 and a1["is_complete"] is True
        assert a1["difference"] == 0                            # slip terakhir menutup selisih Jan–Okt
        # orang yang sama tanpa tanggal keluar: Oktober belum masa terakhir → Sementara
        assert (await tax_forms.build_1721a1(EMP, 2026, 1))["is_complete"] is False

    _with_throwaway_db(body)
