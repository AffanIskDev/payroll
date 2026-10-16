"""Slip signed with a QR code (user 14 Oct 2026, verify.py): every slip has an unguessable code; the QR on its PDF opens a
public page that confirms the slip was approved — no salary figures, the employee's name masked. Since 15 Oct an approved
slip also carries a document number, printed with its issue date under the slip's title and shown on the page with the
issuing and approval status. The pure parts run without a server; the Mongo part runs against a throwaway database that
is dropped afterwards (skipped when MongoDB is not running)."""
import asyncio
import io
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402
from pypdf import PdfReader  # noqa: E402

import pdf_service  # noqa: E402
import verify  # noqa: E402
from test_monthly_components import CFG, EMP  # noqa: E402
from test_rasa_aturan import _slip  # noqa: E402

URL = "https://rasa.rumat.id/verifikasi/AbCdEfGhIjKl"
SIGNER = {"id": "SIGN-00001", "nama": "Meliawasni", "jabatan": "Manager HRD"}


# ---------------------------------------------------------------- the code and the address
def test_codes_are_url_safe_and_do_not_repeat():
    codes = {verify.new_code() for _ in range(2000)}
    assert len(codes) == 2000
    assert all(verify.CODE_RE.match(c) and len(c) == 12 for c in codes)      # 72 bits, short enough for a small QR


@pytest.mark.parametrize("raw,expected", [
    ("https://rasa.rumat.id", "https://rasa.rumat.id"), ("https://rasa.rumat.id/", "https://rasa.rumat.id"),
    (" http://localhost:3800 ", "http://localhost:3800"), ("https://rasa.rumat.id/app/", "https://rasa.rumat.id/app"),
    ("rasa.rumat.id", ""), ("ftp://rasa.rumat.id", ""), ("https://", ""), ("https://rasa rumat.id", ""),
    ("javascript:alert(1)", ""), ("", ""), (None, ""),
])
def test_only_a_real_web_address_is_accepted(raw, expected):
    assert verify.clean_base(raw) == expected


def test_address_comes_from_the_config_then_the_first_frontend_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3800, https://rasa.rumat.id")
    assert verify.base_url({}) == "http://localhost:3800"                      # no config: the frontend of this install
    assert verify.base_url({"SLIP_VERIFY_BASE_URL": "https://rasa.rumat.id/"}) == "https://rasa.rumat.id"
    assert verify.base_url({"SLIP_VERIFY_BASE_URL": "bukan alamat"}) == "http://localhost:3800"   # junk is ignored
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert verify.base_url({}) == "" and verify.url_for("AbCdEfGhIjKl", {}) == ""                # nothing to point to
    assert verify.url_for("AbCdEfGhIjKl", {"SLIP_VERIFY_BASE_URL": "https://rasa.rumat.id"}) == URL
    assert verify.url_for("", {"SLIP_VERIFY_BASE_URL": "https://rasa.rumat.id"}) == ""


@pytest.mark.parametrize("base,local", [
    ("http://localhost:3800", True), ("http://127.0.0.1:3800", True), ("http://192.168.1.20:3800", True),
    ("http://10.0.0.5", True), ("http://172.20.1.1", True), ("https://rasa.rumat.id", False),
    ("http://172.32.1.1", False), ("https://8.8.8.8", False),
])
def test_local_addresses_are_recognised(base, local):
    assert verify.is_local(base) is local


@pytest.mark.parametrize("name,masked", [
    ("Sri Wahyuni Putri", "Sri W. P."), ("Iis Kusmiyati Syafaat", "Iis K. S."), ("  ani   lestari ", "ani L."),
    ("Noviyanto", "Noviyanto"),        # one word = a first name, shown like every first name ('N***' matched nothing)
    ("", "-"), (None, "-")])
def test_the_name_is_masked(name, masked):
    assert verify.mask_name(name) == masked


def test_approving_freezes_the_code_the_address_the_number_and_the_signer(monkeypatch):
    issued = []

    async def fake_next(period):
        issued.append(period.get("id"))
        return f"SG/RUMAT/2026/10/{len(issued):04d}"

    monkeypatch.setattr(verify, "next_doc_number", fake_next)
    slip = {"id": "s1", "employee": {"name": "Iis"}}
    cfg = {"SLIP_VERIFY_BASE_URL": "https://rasa.rumat.id"}
    period = {"id": "p1", "signer": SIGNER}
    st = asyncio.run(verify.stamp(slip, period, cfg))
    assert st["verify_url"] == f"https://rasa.rumat.id/verifikasi/{st['verify_code']}"
    assert st["verify_signer"] == {"nama": "Meliawasni", "jabatan": "Manager HRD"}
    assert st["doc_number"] == "SG/RUMAT/2026/10/0001"
    again = asyncio.run(verify.stamp({**slip, "verify_code": "KodeLamaSaya1", "doc_number": "SG/RUMAT/2026/10/0001"},
                                     period, cfg))
    assert again["verify_code"] == "KodeLamaSaya1"                              # the preview's code stays the slip's code
    assert again["doc_number"] == "SG/RUMAT/2026/10/0001" and issued == ["p1"]  # a number is never issued twice
    assert asyncio.run(verify.stamp(slip, {"id": "p1"}, cfg))["verify_signer"] == {"nama": None, "jabatan": None}


@pytest.mark.parametrize("period,seq,expected", [
    ({"bulan": "2026-09", "company": {"id": "CP-001", "nama": "RUMAT"}}, 1, "SG/RUMAT/2026/09/0001"),
    ({"bulan": "2026-12", "company": {"nama": "Rumat Kita"}}, 237, "SG/RUMATKITA/2026/12/0237"),
    ({"start_date": "2026-10-01", "company": {"id": "CP-003"}}, 12, "SG/CP003/2026/10/0012"),   # older period: no bulan
    ({"start_date": "2026-10-01"}, 1, "SG/RASA/2026/10/0001"),                                  # no company from ROSY
])
def test_the_document_number_names_the_company_the_month_and_the_order(period, seq, expected):
    assert verify.doc_number(period, seq) == expected


# ---------------------------------------------------------------- the QR on the PDF
def _page(slip_kw, signer=SIGNER):
    pdf = pdf_service.render_payslip(_slip(**slip_kw), {"period_name": "Oktober 2026", "signer": signer})
    reader = PdfReader(io.BytesIO(pdf))
    return reader, reader.pages[0]


def test_qr_encodes_the_verification_address():
    d = pdf_service._qr(URL)
    assert d.contents[0].value == URL and d.width == d.height == pdf_service.QR_SIZE


def test_pdf_prints_the_qr_and_a_clickable_address():
    reader, page = _page({"verify_url": URL})
    assert len(reader.pages) == 1                                              # the QR must not push the slip to page 2
    text = " ".join(page.extract_text().split())
    assert "Pindai QR untuk memverifikasi keaslian slip" in text and "rasa.rumat.id/verifikasi/AbCdEfGhIjKl" in text
    assert "Meliawasni" in text and "Manager HRD" in text
    uris = [a.get_object().get("/A", {}).get("/URI") for a in (page.get("/Annots") or [])]
    assert uris == [URL]                                                       # the slip is read on a phone: tap the link
    images = [o for o in page["/Resources"]["/XObject"].values() if o.get_object()["/Subtype"] == "/Image"]
    assert len(images) == 2                                                    # the logos only: the QR is vector


def test_the_approved_encrypted_slip_keeps_the_qr_and_the_link():
    pdf = pdf_service.encrypt_pdf(pdf_service.render_payslip(
        _slip(verify_url=URL), {"period_name": "Oktober 2026", "signer": SIGNER}), "010195")
    reader = PdfReader(io.BytesIO(pdf))
    reader.decrypt("010195")
    assert [a.get_object()["/A"]["/URI"] for a in reader.pages[0]["/Annots"]] == [URL]


def _title_line(slip_kw):
    _, page = _page(slip_kw)
    lines = page.extract_text().splitlines()
    return " ".join(lines[lines.index(next(l for l in lines if "SLIP GAJI KARYAWAN" in l)) + 1].split())


def test_an_approved_slip_prints_its_number_and_issue_date_under_the_title():
    assert _title_line({"status": "approved", "doc_number": "SG/RUMAT/2026/09/0001",
                        "approved_at": "2026-10-15T04:48:48.647501+00:00", "verify_url": URL}) \
        == "No. SG/RUMAT/2026/09/0001 · Diterbitkan 15 Oktober 2026"
    # the date is the WIB date: 23.30 UTC on the 14th is already the 15th in Jakarta
    assert _title_line({"status": "approved", "doc_number": "SG/RUMAT/2026/09/0002",
                        "approved_at": "2026-10-14T23:30:00+00:00"}).endswith("Diterbitkan 15 Oktober 2026")
    # approved before numbers existed: the date only
    assert _title_line({"status": "approved", "approved_at": "2026-10-15T04:48:48+00:00"}) == "Diterbitkan 15 Oktober 2026"


def test_a_draft_says_so_where_the_number_will_be_and_the_layout_does_not_move():
    assert _title_line({"status": "draft", "verify_url": URL}) == \
        "DRAFT — belum disetujui; nomor dokumen diberikan saat disetujui"
    reader, _ = _page({"status": "approved", "doc_number": "SG/RUMAT/2026/09/0001",
                       "approved_at": "2026-10-15T04:48:48+00:00", "verify_url": URL})
    assert len(reader.pages) == 1


def test_a_slip_without_an_address_prints_no_qr_but_still_names_the_signer():
    reader, page = _page({})                                                   # old slip / no address to point to
    text = " ".join(page.extract_text().split())
    assert "Pindai QR" not in text and "Meliawasni" in text
    assert not page.get("/Annots")


# ---------------------------------------------------------------- the public page (Mongo)
def _mongo(monkeypatch, tag):
    """A throwaway database wired into every module that reads it, or a skip when MongoDB is not running."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import core
    import pipeline

    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
    tdb = client[f"rasa_test_{tag}_{uuid.uuid4().hex[:8]}"]
    for mod in (core, pipeline, verify):
        monkeypatch.setattr(mod, "db", tdb)
    return client, tdb


async def _up(client):
    try:
        await client.admin.command("ping")
    except Exception:  # noqa: BLE001
        client.close()
        pytest.skip("MongoDB lokal tidak berjalan")


def test_the_public_page_confirms_an_approved_slip_and_reveals_nothing_else(monkeypatch):
    import routes_verify

    client, tdb = _mongo(monkeypatch, "verify")

    async def run():
        await _up(client)
        try:
            await tdb.payroll_periods.insert_one({
                "id": "p1", "period_name": "Oktober 2026", "company": {"nama": "RUMAT", "nama_legal": "PT Rumah Perawatan Indonesia"},
                "signer": {"nama": "Penandatangan Baru", "jabatan": "Direktur"}})
            await tdb.payslips.insert_many([
                {"id": "s-ok", "payroll_period_id": "p1", "status": "approved", "verify_code": "KodeSahSlip01",
                 "approved_at": "2026-10-14T03:00:00+00:00", "take_home_pay": 9099768, "pph21_amount": 196232,
                 "employee": {"name": "Iis Kusmiyati Syafaat", "nik": "2020051", "bank_account_number": "7123456789"},
                 "verify_signer": {"nama": "Meliawasni", "jabatan": "Manager HRD"}, "doc_number": "SG/RUMAT/2026/10/0007"},
                {"id": "s-draft", "payroll_period_id": "p1", "status": "draft", "verify_code": "KodeDraftSlip1",
                 "take_home_pay": 5000000, "employee": {"name": "Budi Santoso"}},
                {"id": "s-old", "payroll_period_id": "p1", "status": "approved", "verify_code": "KodeLamaSlip01",
                 "approved_at": "2026-10-14T02:00:00+00:00", "employee": {"name": "Noviyanto"}}])

            before = datetime.now(timezone.utc)
            ok = await verify.lookup("KodeSahSlip01")
            checked = datetime.fromisoformat(ok.pop("diperiksa_pada"))           # read from the database right now
            assert before <= checked <= datetime.now(timezone.utc)
            assert ok == {"status": "sah", "dokumen": "Slip Gaji", "id_dokumen": "SG/RUMAT/2026/10/0007",
                          "diterbitkan_pada": "2026-10-14T03:00:00+00:00", "status_penerbitan": "diterbitkan",
                          "status_persetujuan": "disetujui", "perusahaan": "PT Rumah Perawatan Indonesia",
                          "periode": "Oktober 2026", "karyawan": "Iis K. S.",
                          "penandatangan": {"nama": "Meliawasni", "jabatan": "Manager HRD"},   # the one who approved it
                          "kode": "KodeSahSlip01"}
            flat = str(ok)
            for secret in ("9099768", "196232", "2020051", "7123456789", "Syafaat"):  # no pay, no NIK, no account, no full name
                assert secret not in flat

            draft = await verify.lookup("KodeDraftSlip1")                       # a draft says nothing about itself
            assert draft.pop("diperiksa_pada") and draft == {
                "status": "belum_disetujui", "status_penerbitan": "belum_diterbitkan", "status_persetujuan": "menunggu",
                "kode": "KodeDraftSlip1"}
            assert (await verify.lookup("KodeLamaSlip01"))["id_dokumen"] is None  # approved before 15 Oct: no number
            # nothing is taken from the address: one character off, and the slip is unknown
            for bad in ("KodeSahSlip02", "kodeSahSlip01", "TidakAdaKode1", "pendek", "", "a" * 41, "../../etc/passwd",
                        "Kode Dengan Spasi", "KodeSahSlip01'}"):
                assert await verify.lookup(bad) is None, bad

            res = Response()
            assert (await routes_verify.verify_slip("KodeSahSlip01", res))["status"] == "sah"
            assert res.headers["cache-control"] == "no-store"
            with pytest.raises(HTTPException) as e:
                await routes_verify.verify_slip("TidakAdaKode1", Response())
            assert e.value.status_code == 404
        finally:
            await client.drop_database(tdb.name)
            client.close()

    asyncio.run(run())


def test_the_verification_route_needs_no_login_while_the_hr_routes_still_do(monkeypatch):
    from fastapi.testclient import TestClient

    env = dict(os.environ)
    try:
        import server                                                          # loads the real .env: undone below
    finally:
        os.environ.clear()
        os.environ.update(env)                                                 # the other tests keep their own settings

    async def fake_lookup(code):
        return {"status": "sah", "kode": code} if code == "KodeSahSlip01" else None

    monkeypatch.setattr(verify, "lookup", fake_lookup)
    http = TestClient(server.app)                                              # no startup: nothing touches a database
    ok = http.get("/api/verify/KodeSahSlip01")                                 # no Authorization header at all
    assert ok.status_code == 200 and ok.json()["status"] == "sah" and ok.headers["cache-control"] == "no-store"
    assert http.get("/api/verify/TidakAdaKode1").status_code == 404
    for path in ("/api/hr/dashboard/employees", "/api/hr/signer", "/api/hr/periods"):
        assert http.get(path).status_code == 401, path                         # everything else stays behind the login


def test_approving_a_slip_stamps_the_qr_and_the_preview_has_the_same_one(monkeypatch):
    import pipeline

    client, tdb = _mongo(monkeypatch, "approve")
    printed = []

    def fake_pdf(slip, period):
        printed.append(slip)
        return "/dev/null"

    async def fake_queue(*a, **kw):
        return 0

    monkeypatch.setattr(pipeline, "save_encrypted", fake_pdf)
    monkeypatch.setattr(pipeline, "queue_delivery", fake_queue)

    async def run():
        await _up(client)
        try:
            period = {"id": "p1", "period_name": "Oktober 2026", "start_date": "2026-10-01", "end_date": "2026-10-31",
                      "signer": SIGNER, "company": {"nama": "RUMAT"}}
            await tdb.payroll_periods.insert_one({**period})
            await tdb.payroll_configs.insert_one({"config_key": "SLIP_VERIFY_BASE_URL",
                                                  "config_value": "https://rasa.rumat.id"})
            emp = {**EMP, "id": "e1", "name": "Iis Kusmiyati Syafaat", "nik": "2020051", "birth_date": "1995-01-01"}

            # a draft gets its code when it is calculated, and keeps it through every recalculation
            first = await pipeline.recalc_and_save(period, emp, {}, cfg=CFG)
            code = first["verify_code"]
            assert verify.CODE_RE.match(code)
            again = await pipeline.recalc_and_save(period, emp, {}, cfg=CFG)
            assert again["verify_code"] == code
            assert (await tdb.payslips.find_one({"id": first["id"]}))["verify_code"] == code

            # the preview prints the QR of the final slip: same code, address from the Konfigurasi, nothing frozen yet
            import core
            stored = await tdb.payslips.find_one({"id": first["id"]}, {"_id": 0})
            prev = await verify.with_preview(stored, await core.get_configs())
            assert prev["verify_code"] == code and prev["verify_url"] == f"https://rasa.rumat.id/verifikasi/{code}"
            assert "verify_url" not in await tdb.payslips.find_one({"id": first["id"]}, {"_id": 0})
            # a draft calculated before this feature gets its code on first preview and keeps it
            monkeypatch.delenv("CORS_ORIGINS", raising=False)                  # no frontend origin to fall back to either
            await tdb.payslips.update_one({"id": first["id"]}, {"$unset": {"verify_code": ""}})
            old = await verify.with_preview(await tdb.payslips.find_one({"id": first["id"]}, {"_id": 0}), {})
            assert verify.CODE_RE.match(old["verify_code"]) and old["verify_url"] == ""        # no address configured yet
            assert (await tdb.payslips.find_one({"id": first["id"]}))["verify_code"] == old["verify_code"]
            await tdb.payslips.update_one({"id": first["id"]}, {"$set": {"verify_code": code}})

            assert "doc_number" not in prev                                      # a draft has no document number yet

            # approving freezes code + address + number + signer and hands exactly that, already approved, to the PDF
            approved = await pipeline.approve_slip(stored, period, {"id": "u1", "username": "melia", "role": "manager_hrd"})
            frozen = await tdb.payslips.find_one({"id": first["id"]}, {"_id": 0})
            assert frozen["status"] == "approved" and frozen["verify_code"] == code
            assert frozen["verify_url"] == f"https://rasa.rumat.id/verifikasi/{code}"
            assert frozen["verify_signer"] == {"nama": "Meliawasni", "jabatan": "Manager HRD"}
            assert frozen["doc_number"] == "SG/RUMAT/2026/10/0001"
            assert printed[-1]["verify_url"] == frozen["verify_url"] and approved["verify_code"] == code
            assert printed[-1]["status"] == "approved" and printed[-1]["doc_number"] == frozen["doc_number"]
            assert printed[-1]["approved_at"] == frozen["approved_at"]          # the issue date printed = the one stored
            # the next slip approved in the period gets the next number
            other = await pipeline.recalc_and_save(period, {**emp, "id": "e2", "name": "Budi"}, {}, cfg=CFG)
            await pipeline.approve_slip(other, period, {"id": "u1", "username": "melia", "role": "manager_hrd"})
            assert (await tdb.payslips.find_one({"id": other["id"]}))["doc_number"] == "SG/RUMAT/2026/10/0002"

            # an approved slip is never recalculated, and the preview shows it exactly as approved
            assert (await pipeline.recalc_and_save(period, emp, {}, cfg=CFG))["verify_code"] == code
            await tdb.payroll_configs.update_one({"config_key": "SLIP_VERIFY_BASE_URL"},
                                                 {"$set": {"config_value": "https://alamat-baru.example"}})
            shown = await verify.with_preview(frozen, await core.get_configs())
            assert shown["verify_url"] == frozen["verify_url"]                  # the old address stays on a slip already issued
            answer = await verify.lookup(code)
            assert answer["status"] == "sah" and answer["id_dokumen"] == "SG/RUMAT/2026/10/0001"
            assert answer["diterbitkan_pada"] == frozen["approved_at"]
        finally:
            await client.drop_database(tdb.name)
            client.close()

    asyncio.run(run())


def test_the_address_setting_refuses_anything_but_a_web_address(monkeypatch):
    import routes_hr

    client, tdb = _mongo(monkeypatch, "cfg")
    monkeypatch.setattr(routes_hr, "db", tdb)

    async def run():
        await _up(client)
        try:
            await tdb.payroll_configs.insert_one({"config_key": "SLIP_VERIFY_BASE_URL", "config_value": ""})
            for bad in ("rasa.rumat.id", "javascript:alert(1)", "ftp://x.y"):
                with pytest.raises(HTTPException) as e:
                    await routes_hr.update_configs({"SLIP_VERIFY_BASE_URL": bad})
                assert e.value.status_code == 400 and "http" in e.value.detail
            await routes_hr.update_configs({"SLIP_VERIFY_BASE_URL": "https://rasa.rumat.id"})
            await routes_hr.update_configs({"SLIP_VERIFY_BASE_URL": ""})            # blank = use the frontend's own address
        finally:
            await client.drop_database(tdb.name)
            client.close()

    asyncio.run(run())
