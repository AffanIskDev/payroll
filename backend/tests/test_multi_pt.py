"""Multi-PT (6 Nov 2026): satu RUSA, satu DB, PT aktif dari sesi. Yang dikunci di sini:
- data satu PT tidak pernah terbaca/terubah dari PT lain (penyaringan terpusat di core.db);
- tanpa PT aktif, data gaji tidak bisa disentuh sama sekali;
- akses & peran per PT (semua_pt, akses, Master Admin), PT awal saat login, dan token yang terikat PT."""
import asyncio
import os
import uuid

import jwt
import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request

import accounts
import core
from core import TanpaKonteksPT, dengan_pt

_env = dict(os.environ)
try:
    import server   # memuat .env backend yang asli: dibatalkan di bawah supaya tes lain memakai setelannya sendiri
finally:
    os.environ.clear()
    os.environ.update(_env)

PT_UJI = ["CP-901", "CP-902"]


@pytest.fixture
def uji(monkeypatch):
    """Jalankan coroutine dengan DB uji sementara (client Motor baru per event loop, seperti tes DB lain) yang dibungkus
    _DbPT; core/accounts/server memakai DB itu. PT uji CP-901/CP-902 terdaftar aktif."""
    def jalankan(fn):
        async def utama():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
            try:
                await client.admin.command("ping")
            except Exception:  # noqa: BLE001
                client.close()
                pytest.skip("MongoDB lokal tidak berjalan")
            nama = f"rusa_test_multipt_{uuid.uuid4().hex[:8]}"
            raw = client[nama]
            tdb = core._DbPT(raw)
            for mod in (core, accounts, server):
                monkeypatch.setattr(mod, "db", tdb)
            monkeypatch.setattr(core, "raw_db", raw)
            try:
                for i in PT_UJI:
                    await tdb.companies.insert_one({"id": i, "nama": f"PT {i}", "is_active": True})
                return await fn(tdb, raw)
            finally:
                await client.drop_database(nama)
                client.close()
        return asyncio.run(utama())
    return jalankan


# ------------------------------------------------------------------ penyaringan data

def test_data_satu_pt_tidak_terlihat_dari_pt_lain(uji):
    async def f(db, raw):
        with dengan_pt("CP-001"):
            await db.slip_uji.insert_one({"id": "a", "nilai": 1})
        with dengan_pt("CP-003"):
            await db.slip_uji.insert_one({"id": "b", "nilai": 2})
            assert [d["id"] async for d in db.slip_uji.find({}, {"_id": 0})] == ["b"]
            assert await db.slip_uji.find_one({"id": "a"}) is None
            assert await db.slip_uji.count_documents({}) == 1
            # ubah/hapus dari PT lain tidak menyentuh data PT pertama
            assert (await db.slip_uji.update_many({}, {"$set": {"nilai": 99}})).modified_count == 1
            assert (await db.slip_uji.delete_many({"id": "a"})).deleted_count == 0
            agg = [d async for d in db.slip_uji.aggregate([{"$group": {"_id": None, "n": {"$sum": "$nilai"}}}])]
            assert agg[0]["n"] == 99
            assert await db.slip_uji.distinct("id") == ["b"]
        with dengan_pt("CP-001"):
            assert await db.slip_uji.find_one({"id": "a"}, {"_id": 0}) == {"id": "a", "nilai": 1, "company_id": "CP-001"}
    uji(f)


def test_dokumen_baru_dan_upsert_diberi_company_id(uji):
    async def f(db, raw):
        with dengan_pt("CP-003"):
            await db.slip_uji.insert_many([{"id": "x"}, {"id": "y"}])
            await db.slip_uji.update_one({"id": "z"}, {"$setOnInsert": {"id": "z"}}, upsert=True)
            await db.slip_uji.replace_one({"id": "x"}, {"id": "x", "baru": True})
        pts = {d["id"]: d["company_id"] async for d in raw.slip_uji.find({}, {"_id": 0})}
        assert pts == {"x": "CP-003", "y": "CP-003", "z": "CP-003"}
    uji(f)


def test_tanpa_pt_aktif_data_gaji_ditolak(uji):
    async def f(db, raw):
        tok = core._PT.set(None)   # conftest memasang CP-001; tes ini justru tanpa PT
        try:
            with pytest.raises(TanpaKonteksPT):
                await db.slip_uji.find_one({})
            with pytest.raises(TanpaKonteksPT):
                await db.slip_uji.insert_one({"id": "a"})
            with pytest.raises(TanpaKonteksPT):
                db.slip_uji.find({})
        finally:
            core._PT.reset(tok)
    uji(f)


def test_filter_pt_lain_di_dalam_sesi_ditolak(uji):
    async def f(db, raw):
        with dengan_pt("CP-003"):
            with pytest.raises(TanpaKonteksPT):
                await db.slip_uji.find_one({"company_id": "CP-001"})
            assert await db.slip_uji.find_one({"company_id": "CP-003"}) is None   # PT sendiri boleh disebut
    uji(f)


def test_koleksi_global_tidak_disaring():
    tdb = core._DbPT(core.raw_db)
    assert not isinstance(tdb.users, core._KoleksiPT)
    assert not isinstance(tdb.companies, core._KoleksiPT)
    assert isinstance(tdb.payslips, core._KoleksiPT)


def test_semua_pt_hanya_untuk_lintas_pt(uji):
    async def f(db, raw):
        with dengan_pt("CP-001"):
            await db.slip_uji.insert_one({"id": "a"})
        with dengan_pt("CP-003"):
            await db.slip_uji.insert_one({"id": "b"})
        with core.semua_pt():
            assert await db.slip_uji.count_documents({}) == 2
    uji(f)


# ------------------------------------------------------------------ akses per PT

def test_akses_semua_pt_termasuk_pt_baru(uji):
    async def f(db, raw):
        u = {"role": "manager_hrd", "semua_pt": True, "is_active": True}
        assert await core.akses_user(u) == {"CP-901": "manager_hrd", "CP-902": "manager_hrd"}
        await db.companies.insert_one({"id": "CP-903", "nama": "PT baru", "is_active": True})
        assert "CP-903" in await core.akses_user(u)
        await db.companies.update_one({"id": "CP-902"}, {"$set": {"is_active": False}})
        assert "CP-902" not in await core.akses_user(u)
    uji(f)


def test_akses_per_pt_dan_peran_berbeda(uji):
    async def f(db, raw):
        u = {"role": "supervisor", "is_active": True,
             "akses": [{"company_id": "CP-901", "role": "manager_hrd"}, {"company_id": "CP-902", "role": "supervisor"},
                       {"company_id": "CP-999", "role": "manager_hrd"}]}   # PT tak dikenal diabaikan
        assert await core.akses_user(u) == {"CP-901": "manager_hrd", "CP-902": "supervisor"}
    uji(f)


def test_master_admin_dan_nonaktif_tanpa_akses_gaji(uji):
    async def f(db, raw):
        assert await core.akses_user({"role": core.MASTER_ADMIN, "semua_pt": True}) == {}
        assert await core.akses_user({"role": "manager_hrd", "semua_pt": True, "is_active": False}) == {}
    uji(f)


def test_pt_awal_terakhir_lalu_utama_lalu_pertama():
    akses = {"CP-001": "manager_hrd", "CP-003": "manager_hrd"}
    assert core.pt_awal({"pt_terakhir": "CP-003", "pt_utama": "CP-001"}, akses) == "CP-003"
    assert core.pt_awal({"pt_terakhir": "CP-777", "pt_utama": "CP-001"}, akses) == "CP-001"
    assert core.pt_awal({}, akses) == "CP-001"
    assert core.pt_awal({}, {}) is None


def test_akses_sah_validasi(uji):
    async def f(db, raw):
        ok = await accounts._akses_sah("supervisor", [{"company_id": "CP-901", "role": "supervisor"}], False, "CP-902")
        assert ok == {"akses": [{"company_id": "CP-901", "role": "supervisor"}], "semua_pt": False, "pt_utama": "CP-901"}
        semua = await accounts._akses_sah("manager_hrd", None, True, "CP-902")
        assert semua["semua_pt"] is True and semua["akses"] == [] and semua["pt_utama"] == "CP-902"
        assert await accounts._akses_sah(core.MASTER_ADMIN, [{"company_id": "CP-901", "role": "manager_hrd"}], True, "CP-901") \
            == {"akses": [], "semua_pt": False, "pt_utama": None}
        for buruk in ([], [{"company_id": "CP-999", "role": "supervisor"}], [{"company_id": "CP-901", "role": "direktur"}],
                      [{"company_id": "CP-901", "role": "supervisor"}, {"company_id": "CP-901", "role": "manager_hrd"}]):
            with pytest.raises(HTTPException):
                await accounts._akses_sah("supervisor", buruk, False, None)
    uji(f)


# ------------------------------------------------------------------ token & ganti PT

def _request(token):
    return Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})


class _Resp:
    def set_cookie(self, *a, **k):
        pass


async def _pengguna(db):
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "username": "uji.multi", "username_lower": "uji.multi", "name": "Uji", "role": "supervisor",
        "is_active": True, "auth_mode": "local", "access_v2": True, "semua_pt": False, "pt_utama": "CP-901",
        "akses": [{"company_id": "CP-901", "role": "manager_hrd"}, {"company_id": "CP-902", "role": "supervisor"}]})
    return uid


def test_token_membawa_pt_dan_peran_di_pt_itu(uji):
    async def f(db, raw):
        uid = await _pengguna(db)
        tok = core._PT.set(None)
        try:
            u = await core.get_current_user(_request(core.create_access_token(uid, "x", "CP-902")))
            assert u["pt"] == "CP-902" and u["role"] == "supervisor"
            assert core.current_company() == "CP-902"   # konteks db ikut PT token
        finally:
            core._PT.reset(tok)
        u = await core.get_current_user(_request(core.create_access_token(uid, "x", "CP-901")))
        assert u["role"] == "manager_hrd"
    uji(f)


def test_token_pt_tanpa_akses_atau_tanpa_pt_ditolak(uji):
    async def f(db, raw):
        uid = await _pengguna(db)
        for pt in ("CP-001", None):
            with pytest.raises(HTTPException) as e:
                await core.get_current_user(_request(core.create_access_token(uid, "supervisor", pt)))
            assert e.value.status_code == 401
        # akses dicabut sesudah token terbit: berlaku seketika
        tok = core.create_access_token(uid, "supervisor", "CP-902")
        await db.users.update_one({"id": uid}, {"$set": {"akses": [{"company_id": "CP-901", "role": "manager_hrd"}]}})
        with pytest.raises(HTTPException):
            await core.get_current_user(_request(tok))
    uji(f)


def test_ganti_pt_menerbitkan_token_baru_dan_mengingat_pt(uji):
    async def f(db, raw):
        uid = await _pengguna(db)
        me = await core.get_current_user(_request(core.create_access_token(uid, "x", "CP-901")))
        out = await server.ganti_pt(server.PtIn(company_id="CP-902"), _Resp(), me)
        klaim = jwt.decode(out["token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
        assert klaim["pt"] == "CP-902" and klaim["role"] == "supervisor"
        assert out["user"]["pt"]["id"] == "CP-902"
        assert [p["id"] for p in out["user"]["daftar_pt"]] == ["CP-901", "CP-902"]
        assert (await db.users.find_one({"id": uid}))["pt_terakhir"] == "CP-902"
        with pytest.raises(HTTPException) as e:
            await server.ganti_pt(server.PtIn(company_id="CP-001"), _Resp(), me)
        assert e.value.status_code == 403
    uji(f)
