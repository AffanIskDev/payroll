"""Identitas perusahaan dari ROSY v2 (multi-PT, 6 Nov 2026): logo → PNG, identitas ROSY dengan cadangan Konfigurasi,
identitas PT lain tidak menimpa PT aktif, kop slip per PT."""
import asyncio
import io
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image as PILImage

import core
import pdf_service
import perusahaan
from core import dengan_pt


def _gambar(fmt: str) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGBA" if fmt != "JPEG" else "RGB", (40, 20), (200, 30, 30)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_logo_apa_pun_jadi_png(fmt):
    out = perusahaan.ke_png(_gambar(fmt))
    with PILImage.open(io.BytesIO(out)) as im:
        assert im.format == "PNG" and im.mode == "RGBA" and im.size == (40, 20)


def test_logo_besar_diperkecil():
    buf = io.BytesIO()
    PILImage.new("RGB", (3000, 600)).save(buf, format="PNG")
    with PILImage.open(io.BytesIO(perusahaan.ke_png(buf.getvalue()))) as im:
        assert im.size == (1200, 240)


def test_bukan_gambar_ditolak():
    with pytest.raises(Exception):
        perusahaan.ke_png(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")


@pytest.fixture
def uji(monkeypatch, tmp_path):
    monkeypatch.setattr(perusahaan, "LOGOS", tmp_path)

    def jalankan(fn):
        async def utama():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
            try:
                await client.admin.command("ping")
            except Exception:  # noqa: BLE001
                client.close()
                pytest.skip("MongoDB lokal tidak berjalan")
            nama = f"rusa_test_pt_{uuid.uuid4().hex[:8]}"
            tdb = core._DbPT(client[nama])
            for mod in (core, perusahaan):
                monkeypatch.setattr(mod, "db", tdb)
            try:
                await tdb.companies.insert_one({"id": "CP-003", "nama": "RUMI", "nama_legal": "Rumat Mahir Indonesia"})
                return await fn(tdb)
            finally:
                await client.drop_database(nama)
                client.close()
        return asyncio.run(utama())
    return jalankan


def test_identitas_dari_rosy_dengan_cadangan_konfigurasi(uji):
    async def f(db):
        with dengan_pt("CP-003"):
            await db.payroll_configs.insert_many([{"config_key": "COMPANY_NPWP", "config_value": "[NPWP_PEMOTONG]"},
                                                  {"config_key": "COMPANY_ADDRESS", "config_value": "Jl. Cadangan 1"}])
            # belum pernah Fetch: nama dari koleksi companies, NPWP placeholder = kosong, alamat dari cadangan
            i = await perusahaan.identitas()
            assert i["nama_legal"] == "Rumat Mahir Indonesia" and i["npwp"] is None and i["alamat"] == "Jl. Cadangan 1"
            assert i["sumber"]["alamat"] == "rusa" and set(i["kosong"]) == {"npwp", "logo"}
            # sesudah Fetch: ROSY menang atas cadangan
            await perusahaan.simpan_identitas({"id": "CP-003", "nama": "RUMI", "nama_legal": "PT Rumat Mahir Indonesia",
                                               "npwp": "012345678901234", "alamat": "Jl. ROSY 2"})
            i = await perusahaan.identitas()
            assert (i["nama_legal"], i["npwp"], i["alamat"]) == ("PT Rumat Mahir Indonesia", "012345678901234", "Jl. ROSY 2")
            assert i["sumber"] == {"nama_legal": "rosy", "npwp": "rosy", "alamat": "rosy"} and i["kosong"] == ["logo"]
    uji(f)


def test_identitas_pt_lain_tidak_menimpa_pt_aktif(uji):
    async def f(db):
        with dengan_pt("CP-003"):
            await perusahaan.simpan_identitas({"id": "CP-001", "nama_legal": "PT Rumah Perawatan Indonesia", "npwp": "1"})
            await perusahaan.simpan_identitas(None)   # mode mock / feed lama
        assert "rosy" not in (await db.companies.find_one({"id": "CP-003"}))
    uji(f)


def test_segarkan_logo_menyimpan_png_dan_melewati_sidik_sama(uji, monkeypatch):
    panggilan = []

    async def palsu(versi_tersimpan=None):
        panggilan.append(versi_tersimpan)
        return None if versi_tersimpan == "v1" else (_gambar("WEBP"), "v1")
    monkeypatch.setattr(perusahaan.integrations, "fetch_company_logo", palsu)

    async def f(db):
        with dengan_pt("CP-003"):
            assert await perusahaan.segarkan_logo() is None
            assert perusahaan.logo_path("CP-003") is not None
            assert (await db.companies.find_one({"id": "CP-003"}))["logo_versi"] == "v1"
            assert await perusahaan.segarkan_logo() is None   # sidik sama: tidak diunduh/diproses ulang
            assert (await perusahaan.identitas())["logo"] is True
        assert panggilan == [None, "v1"]
    uji(f)


def test_logo_belum_ada_atau_rosy_gagal_tidak_menggagalkan_fetch(uji, monkeypatch):
    async def kosong(versi_tersimpan=None):
        return None, None

    async def gagal(versi_tersimpan=None):
        raise RuntimeError("ROSY 503")

    async def f(db):
        with dengan_pt("CP-003"):
            monkeypatch.setattr(perusahaan.integrations, "fetch_company_logo", kosong)
            assert "belum diatur" in await perusahaan.segarkan_logo()
            monkeypatch.setattr(perusahaan.integrations, "fetch_company_logo", gagal)
            assert "ROSY 503" in await perusahaan.segarkan_logo()
    uji(f)


def test_kop_per_pt(monkeypatch, tmp_path):
    monkeypatch.setattr(perusahaan, "LOGOS", tmp_path)
    ss = pdf_service.getSampleStyleSheet()
    sel = lambda kop: kop._cellvalues[0]   # noqa: E731
    rumat = sel(pdf_service._kop({"company_id": "CP-001"}, ss))
    assert all(isinstance(c, pdf_service.Image) for c in rumat)            # RPI + RUMAT
    tanpa_logo = sel(pdf_service._kop({"company_id": "CP-003", "company": {"nama_legal": "Rumat Mahir & Co"}}, ss))
    assert isinstance(tanpa_logo[0], pdf_service.Paragraph) and "Rumat Mahir &amp; Co" in tanpa_logo[0].text
    (tmp_path / "CP-003.png").write_bytes(perusahaan.ke_png(_gambar("PNG")))
    dengan_logo = sel(pdf_service._kop({"company_id": "CP-003", "company": {"nama_legal": "Rumat Mahir Indonesia"}}, ss))
    assert isinstance(dengan_logo[0], pdf_service.Image) and isinstance(dengan_logo[1], pdf_service.Paragraph)
