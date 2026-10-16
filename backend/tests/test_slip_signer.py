"""Slip signer from ROSY (user 11 Oct 2026): ROSY's payroll Document Signer — since 14 Oct 2026 only its name and position
(the slip is "signed" with a QR code, see test_slip_verify.py, not with the signature image). HAM is stubbed; the Mongo
part runs against a throwaway database that is dropped afterwards (skipped when MongoDB is not running)."""
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
from pypdf import PdfReader  # noqa: E402

import integrations  # noqa: E402
import pdf_service  # noqa: E402
import signer  # noqa: E402
from test_rasa_aturan import _slip  # noqa: E402

SIGNER = {"id": "SIGN-00001", "nama": "Meliawasni", "jabatan": "Manager HRD", "ttd_versi": "42556b352186"}


def test_status_only_needs_a_signer_with_a_name():
    assert signer.status(None) == "tanpa_penandatangan"
    assert signer.status({}) == "tanpa_penandatangan"
    assert signer.status({**SIGNER, "nama": ""}) == "tanpa_penandatangan"
    assert signer.status(SIGNER) == "ada"
    # the signature image of ROSY is no longer needed: a signer without one is complete (user 14 Oct 2026)
    assert signer.status({**SIGNER, "ttd_versi": None}) == "ada"
    assert signer.status({k: v for k, v in SIGNER.items() if k != "ttd_versi"}) == "ada"


def test_the_signature_image_is_no_longer_fetched():
    assert not hasattr(integrations, "fetch_signer_image")
    assert not hasattr(signer, "ensure_image") and not hasattr(pdf_service, "signature_path")


def _text(signer_doc, **slip_kw):
    pdf = pdf_service.render_payslip(_slip(**slip_kw), {"period_name": "Oktober 2026", "signer": signer_doc})
    return PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


def test_slip_pdf_names_the_signer_under_the_qr():
    text = _text(SIGNER, verify_url="https://rasa.rumat.id/verifikasi/AbCdEfGhIjKl")
    assert "Disetujui oleh," in text and "Meliawasni" in text and "Manager HRD" in text
    text = _text(None)                                                # no signer: the block stays empty
    assert "Disetujui oleh," in text and "Meliawasni" not in text


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
        import core
        monkeypatch.setattr(signer, "db", tdb)
        monkeypatch.setattr(core, "db", tdb)  # get_configs (the QR address shown on the Config page)
        try:
            await tdb.payroll_periods.insert_many([
                {"id": "p-draft", "status": "draft", "start_date": "2026-10-01", "signer": old},
                {"id": "p-pending", "status": "pending_approval", "start_date": "2026-09-01", "signer": old},
                {"id": "p-approved", "status": "approved", "start_date": "2026-08-01", "signer": old}])
            # nothing fetched yet since this feature: the Config page shows the newest period's signer
            assert (await signer.current())["signer"] == old

            monkeypatch.setattr(integrations, "fetch_signer", fake_signer)
            out = await signer.refresh()
            assert out["status"] == "ada" and out["signer"] == SIGNER and out["company"]["nama"] == "RUMAT"
            assert "image" not in out and "error" not in out
            got = {p["id"]: p["signer"] async for p in tdb.payroll_periods.find({}, {"_id": 0})}
            assert got["p-draft"] == SIGNER and got["p-pending"] == SIGNER
            assert got["p-approved"] == old                           # approved slips keep the signer they carry
            assert (await signer.current())["fetched_at"]

            # the Config page also tells where the QR on the slips points, and warns when only this computer can open it
            await tdb.payroll_configs.insert_one({"config_key": "SLIP_VERIFY_BASE_URL",
                                                  "config_value": "https://rasa.rumat.id/"})
            cur = await signer.current()
            assert (cur["verify_base"], cur["verify_base_local"]) == ("https://rasa.rumat.id", False)
            await tdb.payroll_configs.update_one({"config_key": "SLIP_VERIFY_BASE_URL"},
                                                 {"$set": {"config_value": "http://localhost:3800"}})
            cur = await signer.current()
            assert (cur["verify_base"], cur["verify_base_local"]) == ("http://localhost:3800", True)
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
