"""Run THR & Bonus Tahunan (user 30 Okt 2026): pajaknya selisih TER atas gaji bulan dibayar, dan Pasal 17 Desember /
1721-A1 menjumlahkan semua run menurut BULAN DIBAYAR. Tes basis data memakai MongoDB sementara yang dibuang sesudahnya
(dilewati bila MongoDB tidak berjalan)."""
import asyncio
import math
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

from engine import compute_payslip, compute_special_slip, special_tax, ter_rate  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
EMP = {"id": "e1", "nik": "2016008", "name": "Contoh Karyawan", "payroll_status": "active", "basic_salary": 4500000,
       "position_allowance": 500000, "monthly_attendance_allowance": 750000, "overtime_hourly_rate": 0,
       "ptkp_status": "TK/0", "birth_date": "1990-01-01"}


@pytest.mark.parametrize("cat", ["A", "B", "C"])
def test_tax_is_ter_difference_and_adds_up_to_ter_of_total(cat):
    base, nominal = 6_000_000, 6_000_000
    t = special_tax(cat, base, nominal)
    gaji_tax = math.floor(base * ter_rate(cat, base) / 100)
    # pajak gaji (run gaji) + pajak run khusus = TER atas bruto gabungan, apa pun urutan pengerjaannya
    assert gaji_tax + t["pph21"] == math.floor((base + nominal) * ter_rate(cat, base + nominal) / 100)
    assert t["pph21"] > math.floor(nominal * ter_rate(cat, nominal) / 100)  # tidak dipajaki sendirian


def test_without_baseline_taxes_the_nominal_alone():
    t = special_tax("A", 0, 6_000_000)
    assert t["baseline_tax"] == 0 and t["pph21"] == math.floor(6_000_000 * ter_rate("A", 6_000_000) / 100)


def test_special_slip_shape():
    s = compute_special_slip(EMP, "bonus_tahunan", 9_000_000, 7_000_000, "slip_bulan_ini")
    assert s["bonus_tahunan"] == 9_000_000 and s["thr"] == 0 and s["run_type"] == "bonus_tahunan"
    assert s["gross_earnings"] == s["taxable_gross"] == 9_000_000
    assert s["take_home_pay"] == 9_000_000 and s["pph21_amount"] == s["total_deductions"] == 0
    assert s["bpjs"]["jht_employee"] == 0 and s["iuran_bpjs_tk_total"] == 0   # THR / bonus tidak kena BPJS
    assert s["special_tax"]["baseline_source"] == "slip_bulan_ini"


def test_special_slip_pays_in_full_and_defers_tax_to_pasal17():
    s = compute_special_slip(EMP, "thr", 9_000_000, 7_000_000, "slip_bulan_ini")
    assert s["pph21_method"] == "ditunda" and s["pph21_withheld"] == 0
    assert s["taxable_gross"] == 9_000_000                    # tetap penghasilan kena pajak untuk rekonsiliasi
    assert s["special_tax"]["pph21"] > 0                      # perkiraan TER selisih hanya informasi


def test_zero_nominal_means_no_tax():
    s = compute_special_slip(EMP, "thr", 0, 6_000_000)
    assert s["pph21_amount"] == 0 and s["take_home_pay"] == 0


def _db(monkeypatch, *modules):
    from motor.motor_asyncio import AsyncIOMotorClient
    name = f"rasa_test_special_{uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
    tdb = client[name]
    for m in modules:
        monkeypatch.setattr(m, "db", tdb)
    return client, tdb, name


async def _gaji(tdb, month, taxable=6_000_000, pph=45_000, status="approved"):
    pid = f"g{month}"
    await tdb.payroll_periods.insert_one({"id": pid, "run_type": "gaji", "bulan": f"2026-{month:02d}",
                                          "start_date": f"2026-{month:02d}-01", "end_date": f"2026-{month:02d}-28",
                                          "period_name": f"Bulan {month} 2026", "created_at": f"2026-{month:02d}-01"})
    slip = compute_payslip(EMP, [], CFG, {})
    await tdb.payslips.insert_one({**slip, "payroll_period_id": pid, "employee_id": "e1", "status": status,
                                   "taxable_gross": taxable, "pph21_amount": pph})
    return pid


async def _special(tdb, run_type, bulan, nominal, created="2026-01-02", employee_id="e1"):
    pid = f"s-{run_type}-{bulan}"
    year, month = int(bulan[:4]), int(bulan[5:])
    await tdb.payroll_periods.insert_one({"id": pid, "run_type": run_type, "bulan": bulan, "start_date": f"{bulan}-15",
                                          "end_date": f"{bulan}-15", "period_name": f"{run_type} {bulan}",
                                          "created_at": created, "employee_ids": [employee_id], "status": "draft"})
    slip = compute_special_slip(EMP, run_type, nominal, 6_000_000, "slip_bulan_ini")
    await tdb.payslips.insert_one({**slip, "payroll_period_id": pid, "employee_id": employee_id, "status": "approved"})
    return pid


def test_december_context_sums_special_runs_by_paid_month(monkeypatch):
    import pipeline
    client, tdb, name = _db(monkeypatch, pipeline)

    async def run():
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            pytest.skip("MongoDB lokal tidak berjalan")
        try:
            await _gaji(tdb, 3)
            await _special(tdb, "thr", "2026-03", 6_000_000)            # dibayar Maret: ikut
            await _special(tdb, "bonus_tahunan", "2026-12", 3_000_000)  # dibayar Desember: ikut
            await _special(tdb, "bonus_tahunan", "2027-01", 9_000_000)  # dibayar Januari tahun depan: TIDAK ikut 2026
            dec = {"id": "gdec", "run_type": "gaji", "bulan": "2026-12", "start_date": "2026-12-01", "end_date": "2026-12-31"}
            ctx = await pipeline.december_context(dec, EMP)
            thr_pph = compute_special_slip(EMP, "thr", 6_000_000, 6_000_000)["pph21_amount"]
            bonus_pph = compute_special_slip(EMP, "bonus_tahunan", 3_000_000, 6_000_000)["pph21_amount"]
            assert ctx["system_gross"] == 6_000_000 + 6_000_000 + 3_000_000
            assert ctx["system_pph21"] == 45_000 + thr_pph + bonus_pph
            assert ctx["system_months"] == 1   # hanya slip gaji yang menambah bulan kerja
            assert ctx["special_gross"] == 9_000_000
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_baseline_prefers_same_month_then_last_then_none(monkeypatch):
    import pipeline
    client, tdb, name = _db(monkeypatch, pipeline)

    async def run():
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            pytest.skip("MongoDB lokal tidak berjalan")
        try:
            run_mar = {"id": "x", "run_type": "thr", "bulan": "2026-03", "created_at": "2026-03-01"}
            assert await pipeline.special_baseline(run_mar, "e1") == (0, "tidak_ada")
            await _gaji(tdb, 2, taxable=5_000_000)
            base, src = await pipeline.special_baseline(run_mar, "e1")
            assert base == 5_000_000 and src.startswith("slip_terakhir")
            await _gaji(tdb, 3, taxable=6_500_000)
            assert await pipeline.special_baseline(run_mar, "e1") == (6_500_000, "slip_bulan_ini")
            # run khusus lain di bulan yang sama, dibuat lebih dulu, menambah dasar; yang dibuat belakangan tidak
            await _special(tdb, "bonus_tahunan", "2026-03", 2_000_000, created="2026-03-02")
            later = {**run_mar, "created_at": "2026-03-05"}
            earlier = {**run_mar, "created_at": "2026-03-01"}
            assert (await pipeline.special_baseline(later, "e1"))[0] == 6_500_000 + 2_000_000
            assert (await pipeline.special_baseline(earlier, "e1"))[0] == 6_500_000
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_1721a1_counts_bonus_tahunan_without_adding_a_working_month(monkeypatch):
    import tax_forms
    client, tdb, name = _db(monkeypatch, tax_forms)

    async def run():
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            pytest.skip("MongoDB lokal tidak berjalan")
        try:
            await _gaji(tdb, 3)
            await _special(tdb, "bonus_tahunan", "2026-03", 3_000_000)
            await _special(tdb, "thr", "2026-03", 4_000_000)
            a1 = await tax_forms.build_1721a1(EMP, 2026, 1)
            assert a1["items"]["i7"] == 7_000_000
            assert a1["months_worked"] == 1
            # i20 = PPh 21 yang dipotong: gaji Maret + tiap run khusus (dasar 6 jt seperti diisi _special)
            paid = 45_000 + sum(compute_special_slip(EMP, k, n, 6_000_000)["pph21_amount"]
                                for k, n in (("bonus_tahunan", 3_000_000), ("thr", 4_000_000)))
            assert a1["items"]["i20"] == paid
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_batch_bsi_label_per_run():
    import bank_batch
    slip = {"employee_id": "e1", "employee": {"nik": "1", "name": "A"}, "take_home_pay": 5_565_000}
    emp = {"e1": {"name": "A", "bank_code": "BSI", "bank_account_number": "7123456789", "bank_account_name": "A"}}
    res = bank_batch.build([slip], emp, "2027-03", "2027-03-02", "THR")
    assert res["problems"] == [] and res["text"].startswith("0|THR2703|2027-03-02|1|5565000|")
    assert "THR MARET 2027" in res["text"]
    assert bank_batch.file_name({"nama": "RUMAT"}, "2027-03", "Bonus Tahunan") == "BatchPayment-RUMAT-Bonus-Tahunan-Maret-2027.txt"
    assert bank_batch.file_name({"nama": "RUMAT"}, "2027-03") == "BatchPayment-RUMAT-Maret-2027.txt"   # gaji: tak berubah


def test_special_run_change_recomputes_only_editable_final_tax_periods(monkeypatch):
    """Run THR / Bonus berubah (user 30 Okt 2026): periode gaji draft yang punya slip Pasal 17 (Desember / karyawan keluar) di
    bulan dibayar atau sesudahnya dihitung ulang; yang TER saja, sudah approved, atau sebelum bulan dibayar dilewati."""
    import pipeline
    client, tdb, name = _db(monkeypatch, pipeline)
    called = []

    async def fake_process(period):
        called.append(period["bulan"])
        return 1
    monkeypatch.setattr(pipeline, "process_period", fake_process)

    async def periode(bulan, status, method, pid=None):
        pid = pid or f"p{bulan}"
        await tdb.payroll_periods.insert_one({"id": pid, "run_type": "gaji", "bulan": bulan, "status": status})
        await tdb.payslips.insert_one({"payroll_period_id": pid, "employee_id": "e1", "pph21_method": method})

    async def run():
        try:
            await client.admin.command("ping")
            await periode("2026-10", "draft", "pasal17")     # karyawan keluar Oktober: ikut
            await periode("2026-11", "draft", "ter")         # TER saja: tidak perlu
            await periode("2026-12", "draft", "pasal17")     # Desember: ikut
            await periode("2026-09", "draft", "pasal17")     # sebelum bulan dibayar: tidak
            await periode("2026-11", "approved", "pasal17", "pa")  # sudah approved: tidak
            assert await pipeline.recompute_final_tax_periods("2026-10") == ["2026-10", "2026-12"]
            assert called == ["2026-10", "2026-12"]
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_amounts_from_gapok_fill_multiplier_times_basic_salary(monkeypatch):
    """Pilihan "Ambil dari Gaji Pokok" (user 31 Okt 2026): nominal = gaji pokok kontrak x pengali, jadi input RUSA; karyawan
    tanpa gaji pokok dilewati; pengali di luar batas ditolak."""
    import pipeline
    import special_runs
    from fastapi import HTTPException
    client, tdb, name = _db(monkeypatch, special_runs, pipeline)

    async def fake_process(period):
        return 2
    async def fake_recompute(bulan):
        return []
    monkeypatch.setattr(special_runs, "process_special", fake_process)
    monkeypatch.setattr(special_runs, "recompute_final_tax_periods", fake_recompute)

    async def run():
        try:
            await client.admin.command("ping")
            await tdb.employees.insert_many([
                {"id": "a", "name": "A", "basic_salary": 4_000_000}, {"id": "b", "name": "B", "basic_salary": 0},
                {"id": "c", "name": "C", "basic_salary": 3_450_000.0}])
            await tdb.payroll_periods.insert_one({"id": "p1", "run_type": "thr", "bulan": "2026-12", "status": "draft",
                                                  "employee_ids": ["a", "b", "c"]})
            await tdb.special_inputs.insert_one({"id": "old", "payroll_period_id": "p1", "employee_id": "a", "nominal": 1})
            res = await special_runs.amounts_from_gapok("p1", special_runs.FromGapokIn(multiplier=1.5))
            assert res["filled"] == 2 and res["no_gapok"] == ["B"]
            got = {d["employee_id"]: d["nominal"] async for d in tdb.special_inputs.find({"payroll_period_id": "p1"})}
            assert got == {"a": 6_000_000, "c": 5_175_000}     # input lama "a" ditimpa; "b" tak dibuat
            with pytest.raises(HTTPException):
                await special_runs.amounts_from_gapok("p1", special_runs.FromGapokIn(multiplier=0))
            await tdb.payroll_periods.update_one({"id": "p1"}, {"$set": {"status": "approved"}})
            with pytest.raises(HTTPException):
                await special_runs.amounts_from_gapok("p1", special_runs.FromGapokIn(multiplier=1))
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())


def test_excluded_employees_get_no_slip_and_keep_their_nominal(monkeypatch):
    """Kecualikan karyawan dari run (user 31 Okt 2026): tidak dapat slip walau nominalnya ada, nominal tidak hilang sehingga
    menyertakan kembali memulihkannya, "Ambil dari Gaji Pokok" melewati mereka, dan karyawan di luar populasi ditolak."""
    import pipeline
    import special_runs
    from fastapi import HTTPException
    client, tdb, name = _db(monkeypatch, special_runs, pipeline)

    async def fake_process(period):
        return 0
    async def fake_recompute(bulan):
        return []
    monkeypatch.setattr(special_runs, "process_special", fake_process)
    monkeypatch.setattr(special_runs, "recompute_final_tax_periods", fake_recompute)

    async def run():
        try:
            await client.admin.command("ping")
            await tdb.employees.insert_many([{"id": "a", "name": "A", "basic_salary": 4_000_000},
                                             {"id": "b", "name": "B", "basic_salary": 5_000_000}])
            await tdb.payroll_periods.insert_one({"id": "p1", "run_type": "thr", "bulan": "2026-12", "status": "draft",
                                                  "employee_ids": ["a", "b"]})
            await tdb.special_inputs.insert_one({"id": "i", "payroll_period_id": "p1", "employee_id": "a", "nominal": 700})
            await special_runs.set_excluded("p1", special_runs.ExcludeIn(employee_ids=["a"]))
            await special_runs.set_excluded("p1", special_runs.ExcludeIn(employee_ids=["a"]))   # dua kali: tidak ganda
            assert (await tdb.payroll_periods.find_one({"id": "p1"}))["excluded_ids"] == ["a"]
            assert "a" not in await pipeline.special_amounts(await pipeline.get_period("p1"))
            res = await special_runs.amounts_from_gapok("p1", special_runs.FromGapokIn(multiplier=1))
            assert res["filled"] == 1
            assert (await tdb.special_inputs.find_one({"employee_id": "a"}))["nominal"] == 700   # tidak ditimpa
            await special_runs.set_excluded("p1", special_runs.ExcludeIn(employee_ids=["a"], excluded=False))
            assert (await pipeline.special_amounts(await pipeline.get_period("p1")))["a"] == (700.0, "rusa")
            with pytest.raises(HTTPException):
                await special_runs.set_excluded("p1", special_runs.ExcludeIn(employee_ids=["x"]))
            await tdb.payroll_periods.update_one({"id": "p1"}, {"$set": {"status": "approved"}})
            with pytest.raises(HTTPException):
                await special_runs.set_excluded("p1", special_runs.ExcludeIn(employee_ids=["a"]))
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
