"""Slip signer from ROSY (user 11 Oct 2026): the signature image of ROSY's payroll Document Signer is fetched once per
file version, kept on disk and printed on the slip PDF (preview and approved). HAM is stubbed; the Mongo part runs
against a throwaway database that is dropped afterwards (skipped when MongoDB is not running)."""
import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402
from pypdf import PdfReader  # noqa: E402

import integrations  # noqa: E402
import pdf_service  # noqa: E402
import signer  # noqa: E402
from test_rasa_aturan import _slip  # noqa: E402

VER = "42556b352186"
SIGNER = {"id": "SIGN-00001", "nama": "Meliawasni", "jabatan": "Manager HRD", "ttd_versi": VER}


def _png(size=(300, 200)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGBA", size, (0, 0, 0, 0))  # transparent background like ROSY's signature files
    img.paste((20, 30, 120, 255), (40, 90, 260, 110))
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def sign_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_service, "SIGNATURES", tmp_path / "signatures")
    return tmp_path / "signatures"


def _fetcher(monkeypatch, result) -> list:
    calls = []

    async def fake():
        calls.append(1)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(integrations, "fetch_signer_image", fake)
    return calls


def test_image_is_fetched_once_per_version_and_kept_as_png(monkeypatch, sign_dir):
    calls = _fetcher(monkeypatch, (_png(), VER))
    assert signer.status(SIGNER) == "belum_terambil"
    assert asyncio.run(signer.ensure_image(SIGNER)) is None
    assert signer.status(SIGNER) == "ada"
    assert Image.open(sign_dir / f"SIGN-00001-{VER}.png").format == "PNG"
    asyncio.run(signer.ensure_image(SIGNER))
    assert len(calls) == 1                                            # cached: HAM is not asked again
    assert signer.status({**SIGNER, "ttd_versi": "0123456789ab"}) == "belum_terambil"  # re-upload in ROSY


@pytest.mark.parametrize("result, reason", [
    (None, "tidak dapat menyediakan"),                                # HAM 404 (locally: OSS not reachable)
    (RuntimeError("HAM 500"), "tidak dapat dihubungi"),
    ((b"<html>bukan gambar</html>", VER), "bukan gambar"),
    ((_png(), "ffffffffffff"), "baru saja diganti"),                  # signer changed between the two calls
])
def test_missing_image_is_reported_never_raised(monkeypatch, sign_dir, result, reason):
    _fetcher(monkeypatch, result)
    assert reason in asyncio.run(signer.ensure_image(SIGNER))
    assert signer.status(SIGNER) == "belum_terambil"
    assert not list(sign_dir.glob("*.png"))


def test_no_signer_or_no_signature_needs_no_fetch(monkeypatch):
    calls = _fetcher(monkeypatch, (_png(), VER))
    assert asyncio.run(signer.ensure_image(None)) is None
    assert asyncio.run(signer.ensure_image({**SIGNER, "ttd_versi": None})) is None
    assert not calls
    assert signer.status(None) == "tanpa_penandatangan"
    assert signer.status({**SIGNER, "ttd_versi": None}) == "belum_ada_ttd"
    old_sync = {k: v for k, v in SIGNER.items() if k != "ttd_versi"}   # period synced before this feature
    assert signer.status(old_sync) == "belum_terambil"


def test_unsafe_ids_never_reach_the_disk(monkeypatch):
    calls = _fetcher(monkeypatch, (_png(), VER))
    bad = {**SIGNER, "id": "../../etc/passwd"}
    assert pdf_service.signature_path(bad) is None
    assert "tidak dikenali" in asyncio.run(signer.ensure_image(bad))
    assert not calls


def _page(signer_doc):
    pdf = pdf_service.render_payslip(_slip(), {"period_name": "Oktober 2026", "signer": signer_doc})
    page = PdfReader(io.BytesIO(pdf)).pages[0]
    images = [o for o in page["/Resources"]["/XObject"].values() if o.get_object()["/Subtype"] == "/Image"]
    return page.extract_text(), len(images)


def test_slip_pdf_prints_the_signature(monkeypatch):
    text, images = _page(SIGNER)
    assert images == 2 and "Meliawasni" in text                       # logos only: the space stays empty
    _fetcher(monkeypatch, (_png(), VER))
    asyncio.run(signer.ensure_image(SIGNER))
    text, images = _page(SIGNER)
    assert images == 3 and "Meliawasni" in text and "Manager HRD" in text
    reader = PdfReader(io.BytesIO(pdf_service.encrypt_pdf(
        pdf_service.render_payslip(_slip(), {"period_name": "Oktober 2026", "signer": SIGNER}), "010195")))
    reader.decrypt("010195")                                          # the approved (encrypted) slip carries it too
    assert len([o for o in reader.pages[0]["/Resources"]["/XObject"].values()
                if o.get_object()["/Subtype"] == "/Image"]) == 3


def test_refresh_updates_open_periods_and_keeps_approved_ones(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient

    name = f"rasa_test_signer_{uuid.uuid4().hex[:8]}"
    old = {"id": "SIGN-00009", "nama": "Penandatangan Lama", "jabatan": "HRD", "ttd_versi": "aaaaaaaaaaaa"}

    async def fake_signer():
        return SIGNER, {"id": "CP-001", "nama": "RUMAT"}

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(signer, "db", tdb)
        try:
            await tdb.payroll_periods.insert_many([
                {"id": "p-draft", "status": "draft", "start_date": "2026-10-01", "signer": old},
                {"id": "p-pending", "status": "pending_approval", "start_date": "2026-09-01", "signer": old},
                {"id": "p-approved", "status": "approved", "start_date": "2026-08-01", "signer": old}])
            # nothing fetched yet since this feature: the Config page shows the newest period's signer
            assert (await signer.current())["signer"] == old

            monkeypatch.setattr(integrations, "fetch_signer", fake_signer)
            _fetcher(monkeypatch, (_png(), VER))
            out = await signer.refresh()
            assert out["status"] == "ada" and out["image"].startswith("data:image/png;base64,")
            assert out["signer"] == SIGNER and out["company"]["nama"] == "RUMAT" and out["error"] is None
            got = {p["id"]: p["signer"] async for p in tdb.payroll_periods.find({}, {"_id": 0})}
            assert got["p-draft"] == SIGNER and got["p-pending"] == SIGNER
            assert got["p-approved"] == old                           # approved slips keep the signer they carry
            assert (await signer.current())["fetched_at"]
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
