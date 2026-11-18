"""Gaji diinput di RUSA (18 Nov 2026, gaji_rusa.py): per PT, GAJI_SUMBER=rusa membuat gaji dari RUSA, identitas tetap dari
ROSY. Yang dikunci di sini:
- mode rosy (bawaan, RUMAT) tidak berubah: Fetch tidak minta tanpa_kontrak, gaji ROSY dipakai;
- mode rusa: gaji ROSY TIDAK dipakai; karyawan tanpa gaji RUSA disimpan tapi tidak ikut periode (meta.dilewati);
- simpan gaji: validasi, riwayat, dokumen employees langsung ikut; ditolak di mode rosy;
- Salin dari ROSY hanya mengisi yang belum diisi; gaji satu PT tidak terbaca dari PT lain."""
import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

import core
import gaji_rusa
import integrations
import perusahaan
import routes_hr
from core import dengan_pt


def _baris(rid, nama, kontrak=True, gapok=5000000.0):
    return {"rosy_employee_id": rid, "nik": rid, "name": nama, "email": "", "department": "Perawat", "position": "",
            "ptkp_status": "TK/0", "payroll_status": "active", "basic_salary": gapok if kontrak else 0.0,
            "position_allowance": 1000000.0 if kontrak else 0.0, "monthly_attendance_allowance": 0.0,
            "overtime_hourly_rate": 0.0, "has_bpjs_kes": kontrak, "has_bpjs_tk": kontrak,
            "bpjs_programs": {p: kontrak for p in gaji_rusa.PROGRAMS}, "jkk_rate": 0.0024,
            "overtime_access": True, "data_issues": ["gaji_pokok_nol"] if not kontrak else [],
            "punya_kontrak_rosy": kontrak}


ROSY = [_baris("USRD-1", "Dini"), _baris("USRD-2", "Hasrawati", kontrak=False)]
USER = {"id": "u1", "username": "syafitri", "role": "supervisor"}


@pytest.fixture
def uji(monkeypatch):
    diminta = []

    async def feed(periode, tanpa_kontrak=False):
        diminta.append(tanpa_kontrak)
        return [dict(r, bpjs_programs=dict(r["bpjs_programs"]), data_issues=list(r["data_issues"])) for r in ROSY], \
            {"dilewati": [], "company": None}

    async def kosong(*a, **k):
        return None

    monkeypatch.setattr(integrations, "fetch_employees", feed)
    monkeypatch.setattr(perusahaan, "simpan_identitas", kosong)
    monkeypatch.setattr(perusahaan, "segarkan_logo", kosong)

    def jalankan(fn):
        async def utama():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
            try:
                await client.admin.command("ping")
            except Exception:  # noqa: BLE001
                client.close()
                pytest.skip("MongoDB lokal tidak berjalan")
            nama = f"rusa_test_gaji_{uuid.uuid4().hex[:8]}"
            tdb = core._DbPT(client[nama])
            for mod in (core, gaji_rusa, routes_hr):
                monkeypatch.setattr(mod, "db", tdb)
            try:
                return await fn(tdb, diminta)
            finally:
                await client.drop_database(nama)
                client.close()
        return asyncio.run(utama())
    return jalankan


async def _mode(db, nilai):
    await db.payroll_configs.update_one({"config_key": "GAJI_SUMBER"}, {"$set": {"config_value": nilai}}, upsert=True)


def test_mode_rosy_tidak_berubah(uji):
    async def f(db, diminta):
        with dengan_pt("CP-001"):
            ids, meta = await routes_hr.sync_employees("2026-11")
            assert diminta == [False]
            assert len(ids) == 2   # feed lama tak pernah mengirim yang tanpa kontrak; di sini keduanya ikut apa adanya
            dini = await db.employees.find_one({"rosy_employee_id": "USRD-1"}, {"_id": 0})
            assert (dini["basic_salary"], dini["gaji_sumber"], dini["gaji_ada"]) == (5000000, "rosy", True)
            with pytest.raises(HTTPException) as e:
                await gaji_rusa.ubah(dini["id"], gaji_rusa.GajiIn(basic_salary=1), USER)
            assert e.value.status_code == 409
    uji(f)


def test_mode_rusa_gaji_rosy_tidak_dipakai_dan_yang_belum_diisi_tak_ikut(uji):
    async def f(db, diminta):
        with dengan_pt("CP-003"):
            await _mode(db, "rusa")
            ids, meta = await routes_hr.sync_employees("2026-11")
            assert diminta == [True]
            assert ids == []   # belum ada yang diisi di RUSA — kontrak ROSY Dini TIDAK dipakai diam-diam
            assert {d["name"]: d["alasan"] for d in meta["dilewati"]} == {"Dini": gaji_rusa.ALASAN_BELUM,
                                                                          "Hasrawati": gaji_rusa.ALASAN_BELUM}
            dini = await db.employees.find_one({"rosy_employee_id": "USRD-1"}, {"_id": 0})
            assert (dini["basic_salary"], dini["gaji_ada"], dini["has_bpjs_kes"]) == (0, False, False)
            assert dini["gaji_rosy"]["basic_salary"] == 5000000   # disimpan untuk Salin dari ROSY
            has = await db.employees.find_one({"rosy_employee_id": "USRD-2"}, {"_id": 0})
            assert has["gaji_rosy"] is None
            assert (await gaji_rusa.info()) == {"sumber": "rusa", "belum": 2, "bisa_salin": 1}

            # isi gaji Hasrawati di RUSA → langsung tampil, lalu ikut periode sesudah Fetch
            baru = await gaji_rusa.ubah(has["id"], gaji_rusa.GajiIn(
                basic_salary=4800000.4, position_allowance=500000, monthly_attendance_allowance=750000,
                overtime_hourly_rate=30000, bpjs_programs={"kes": True, "jht": True}, jkk_rate=0.0054, catatan="SK Nov"), USER)
            assert (baru["basic_salary"], baru["has_bpjs_kes"], baru["has_bpjs_tk"], baru["jkk_rate"]) == (4800000, True, True, 0.0054)
            assert baru["bpjs_programs"] == {"kes": True, "jkk": False, "jkm": False, "jht": True, "jp": False}
            assert "gaji_pokok_nol" not in baru["data_issues"]
            ids, meta = await routes_hr.sync_employees("2026-11")
            assert len(ids) == 1 and [d["name"] for d in meta["dilewati"]] == ["Dini"]
            has = await db.employees.find_one({"rosy_employee_id": "USRD-2"}, {"_id": 0})
            assert (has["basic_salary"], has["overtime_hourly_rate"], has["gaji_ada"], has["gaji_diubah_oleh"]) == \
                (4800000, 30000, True, "syafitri")

            # simpan ulang nilai sama: tak menambah riwayat; nilai beda: riwayat sebelum → sesudah
            await gaji_rusa.ubah(has["id"], gaji_rusa.GajiIn(
                basic_salary=4800000, position_allowance=500000, monthly_attendance_allowance=750000,
                overtime_hourly_rate=30000, bpjs_programs={"kes": True, "jht": True}, jkk_rate=0.0054), USER)
            await gaji_rusa.ubah(has["id"], gaji_rusa.GajiIn(basic_salary=5000000, jkk_rate=0.0054), USER)
            r = await gaji_rusa.detail(has["id"])
            assert [x["sesudah"]["basic_salary"] for x in r["riwayat"]] == [5000000, 4800000]
            assert r["riwayat"][1]["sebelum"] is None and r["riwayat"][1]["catatan"] == "SK Nov"
            assert r["riwayat"][0]["sebelum"]["basic_salary"] == 4800000
    uji(f)


def test_validasi_gaji(uji):
    async def f(db, diminta):
        with dengan_pt("CP-003"):
            await _mode(db, "rusa")
            await routes_hr.sync_employees("2026-11")
            e = await db.employees.find_one({"rosy_employee_id": "USRD-2"}, {"_id": 0})
            for body, pesan in ((gaji_rusa.GajiIn(basic_salary=0), "Gaji pokok"),
                                (gaji_rusa.GajiIn(basic_salary=1, jkk_rate=0.01), "Tarif JKK"),
                                (gaji_rusa.GajiIn(basic_salary=1, bpjs_programs={"jkn": True}), "tidak dikenal")):
                with pytest.raises(HTTPException) as x:
                    await gaji_rusa.ubah(e["id"], body, USER)
                assert x.value.status_code == 400 and pesan in x.value.detail
            with pytest.raises(Exception):
                gaji_rusa.GajiIn(basic_salary=-5)
            with pytest.raises(HTTPException) as x:
                await gaji_rusa.ubah("tidak-ada", gaji_rusa.GajiIn(basic_salary=1), USER)
            assert x.value.status_code == 404
    uji(f)


def test_salin_dari_rosy_hanya_yang_belum_dan_per_pt(uji):
    async def f(db, diminta):
        with dengan_pt("CP-003"):
            await _mode(db, "rusa")
            await routes_hr.sync_employees("2026-11")
            r = await gaji_rusa.salin_semua({**USER, "role": "manager_hrd", "username": "Melia"})
            assert (r["disalin"], r["belum"], r["bisa_salin"]) == (1, 1, 0)   # Hasrawati tak punya kontrak ROSY
            g = await db.gaji_karyawan.find_one({"rosy_employee_id": "USRD-1"}, {"_id": 0})
            assert (g["basic_salary"], g["position_allowance"], g["bpjs_programs"]["jp"], g["updated_by"]) == \
                (5000000, 1000000, True, "Melia")
            assert (await gaji_rusa.salin_semua({**USER, "username": "Melia"}))["disalin"] == 0   # tak menimpa
            ids, _ = await routes_hr.sync_employees("2026-11")
            assert len(ids) == 1
        with dengan_pt("CP-002"):
            assert await db.gaji_karyawan.count_documents({}) == 0
            assert (await gaji_rusa.info()) == {"sumber": "rosy"}
    uji(f)


def test_terapkan_menghitung_ulang_masalah_gaji():
    r = {"basic_salary": 0, "overtime_access": True, "data_issues": ["gaji_pokok_nol", "lembur_tanpa_tarif", "npwp_kosong"]}
    out = gaji_rusa.terapkan(r, {"basic_salary": 4000000, "overtime_hourly_rate": 25000, "bpjs_programs": {"jp": True}})
    assert out["data_issues"] == ["npwp_kosong"]
    assert (out["has_bpjs_kes"], out["has_bpjs_tk"], out["jkk_rate"]) == (False, True, 0.0024)
    assert gaji_rusa.terapkan({**r, "overtime_access": True}, {"basic_salary": 1})["data_issues"] == \
        ["npwp_kosong", "lembur_tanpa_tarif"]


# ------------------------------------------------------------------ Tambahan Bulanan diinput di RUSA (tambahan_rusa.py)

import pipeline  # noqa: E402
import tambahan_rusa  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}


async def _siap_periode(db, monkeypatch, status="draft"):
    """PT RUSA dengan Dini (gaji disalin dari ROSY) & Hasrawati (gaji belum diisi), satu periode gaji Nov 2026."""
    for mod in (pipeline, tambahan_rusa):
        monkeypatch.setattr(mod, "db", db)
    for k, v in CFG.items():
        await db.payroll_configs.update_one({"config_key": k}, {"$set": {"config_value": v}}, upsert=True)
    await _mode(db, "rusa")
    await routes_hr.sync_employees("2026-11")
    await gaji_rusa.salin_semua({**USER, "username": "Melia"})
    ids, _ = await routes_hr.sync_employees("2026-11")
    period = {"id": "p-nov", "run_type": "gaji", "bulan": "2026-11", "period_name": "November 2026",
              "start_date": "2026-11-01", "end_date": "2026-11-30", "status": status, "employee_ids": ids}
    await db.payroll_periods.insert_one(dict(period))
    dini = await db.employees.find_one({"rosy_employee_id": "USRD-1"}, {"_id": 0})
    has = await db.employees.find_one({"rosy_employee_id": "USRD-2"}, {"_id": 0})
    slip = await pipeline.recalc_and_save(period, dini, {"kpi_incentive": 0})
    return period, dini, has, slip


def _isi(eid, **kode):
    return tambahan_rusa.SimpanIn(items=[tambahan_rusa.ItemIn(employee_id=eid, kode=k, nominal=v) for k, v in kode.items()],
                                  catatan="uji")


def test_tambahan_bulanan_langsung_masuk_slip_dan_riwayat(uji, monkeypatch):
    async def f(db, diminta):
        with dengan_pt("CP-003"):
            period, dini, _, awal = await _siap_periode(db, monkeypatch)
            assert (awal["additional_bonus"], awal["loan_installment"]) == (0, 0)
            r = await tambahan_rusa.simpan("p-nov", _isi(dini["id"], BONUS=1000000, LOAN_INSTALLMENT=250000), USER)
            assert r["diubah"] == 1 and r["total"]["BONUS"] == 1000000
            slip = await db.payslips.find_one({"payroll_period_id": "p-nov", "employee_id": dini["id"]}, {"_id": 0})
            assert (slip["additional_bonus"], slip["loan_installment"]) == (1000000, 250000)
            # bonus masuk pendapatan (dan PPh 21), cicilan memotong THP
            assert slip["gross_earnings"] == awal["gross_earnings"] + 1000000
            assert slip["take_home_pay"] == awal["take_home_pay"] + 1000000 - 250000 - (slip["pph21_amount"] - awal["pph21_amount"])
            # sama persis dengan nilai yang sama dari ROSY (period_components) — engine tak membedakan sumbernya
            assert (await pipeline.build_slip(period, dini, {}, CFG))["take_home_pay"] == slip["take_home_pay"]

            # 0 = hapus; nilai yang tidak berubah tidak menambah riwayat
            await tambahan_rusa.simpan("p-nov", _isi(dini["id"], BONUS=1000000, LOAN_INSTALLMENT=0), USER)
            assert await db.komponen_bulanan.count_documents({}) == 1
            slip = await db.payslips.find_one({"payroll_period_id": "p-nov", "employee_id": dini["id"]}, {"_id": 0})
            assert slip["loan_installment"] == 0
            h = await tambahan_rusa.riwayat("p-nov")
            # dua simpanan pertama punya waktu yang sama: bandingkan sebagai himpunan; yang terbaru di atas
            assert h[0]["kode"] == "LOAN_INSTALLMENT" and (h[0]["sebelum"], h[0]["sesudah"]) == (250000, 0)
            assert sorted((x["kode"], x["sebelum"], x["sesudah"]) for x in h) == [
                ("BONUS", 0, 1000000), ("LOAN_INSTALLMENT", 0, 250000), ("LOAN_INSTALLMENT", 250000, 0)]
            assert {x["oleh"] for x in h} == {"syafitri"} and h[0]["catatan"] == "uji"

            # Fetch berikutnya membangun period_components dari input RUSA bulan ini (bukan dari ROSY)
            docs = await tambahan_rusa.docs_periode(period, {"USRD-1": dini["id"]})
            assert [(d["kode"], d["nominal"]) for d in docs] == [("BONUS", 1000000)]
            d = await tambahan_rusa.daftar("p-nov")
            assert d["bisa_ubah"] and [r["name"] for r in d["rows"]] == ["Dini"] and d["rows"][0]["nilai"]["BONUS"] == 1000000
    uji(f)


def test_tambahan_bulanan_ditolak(uji, monkeypatch):
    async def f(db, diminta):
        with dengan_pt("CP-003"):
            period, dini, has, _ = await _siap_periode(db, monkeypatch)
            for body, kode in ((_isi(has["id"], BONUS=1), 400),          # gaji belum diisi → tak ada di periode
                               (_isi(dini["id"], THR=1), 400)):          # THR punya run sendiri
                with pytest.raises(HTTPException) as x:
                    await tambahan_rusa.simpan("p-nov", body, USER)
                assert x.value.status_code == kode
            with pytest.raises(Exception):
                tambahan_rusa.ItemIn(employee_id="x", kode="BONUS", nominal=-1)
            await db.payroll_periods.update_one({"id": "p-nov"}, {"$set": {"status": "pending_approval"}})
            with pytest.raises(HTTPException) as x:
                await tambahan_rusa.simpan("p-nov", _isi(dini["id"], BONUS=1), USER)
            assert x.value.status_code == 400
            assert (await tambahan_rusa.daftar("p-nov"))["bisa_ubah"] is False
            await db.payroll_periods.update_one({"id": "p-nov"}, {"$set": {"status": "draft"}})
            await _mode(db, "rosy")
            with pytest.raises(HTTPException) as x:
                await tambahan_rusa.simpan("p-nov", _isi(dini["id"], BONUS=1), USER)
            assert x.value.status_code == 409
    uji(f)


def test_mode_rusa_mengabaikan_tambahan_bulanan_rosy(uji, monkeypatch):
    async def feed(periode, tanpa_kontrak=False):
        r = dict(ROSY[0], bpjs_programs=dict(ROSY[0]["bpjs_programs"]))
        return [r], {"dilewati": [], "company": None, "components": {"USRD-1": {"BONUS": 777.0}}}
    monkeypatch.setattr(integrations, "fetch_employees", feed)

    async def f(db, diminta):
        with dengan_pt("CP-003"):
            _, meta = await routes_hr.sync_employees("2026-11")
            assert meta["components"] == {"USRD-1": {"BONUS": 777.0}}   # mode ROSY: tetap dipakai
            await _mode(db, "rusa")
            _, meta = await routes_hr.sync_employees("2026-11")
            assert meta["components"] == {}
    uji(f)
