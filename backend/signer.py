"""Slip signer (penandatangan) from ROSY: HAM's payroll Document Signer and its signature image.

ROSY stays the one place to manage signers (HRD: Penandatangan Dokumen); RASA shows them and prints them. The image
is cached on disk per signer and file version (HAM's ttd_versi changes on every re-upload), so the PDF never needs HAM
at approve time and a slip rendered again later keeps the signature it was approved with (user request 11 Oct 2026)."""
import base64
import io
import logging
from typing import Optional

from PIL import Image

from core import db, now_iso
import integrations
import pdf_service
from pdf_service import signature_path

logger = logging.getLogger("signer")


def status(signer: Optional[dict]) -> str:
    """tanpa_penandatangan | belum_ada_ttd (the ROSY signer has no signature) | ada | belum_terambil"""
    if not signer:
        return "tanpa_penandatangan"
    if "ttd_versi" not in signer:  # synced before signatures were fetched (11 Oct 2026): unknown, not missing
        return "belum_terambil"
    if not signer["ttd_versi"]:
        return "belum_ada_ttd"
    return "ada" if signature_path(signer) else "belum_terambil"


def _store(sid: str, ver: str, data: bytes) -> None:
    """Keeps the image as PNG (transparency kept); anything Pillow cannot read is refused."""
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        img = img.convert("RGBA")
    folder = pdf_service.SIGNATURES
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{sid}-{ver}.tmp"
    img.save(tmp, "PNG")
    tmp.replace(folder / f"{sid}-{ver}.png")


async def ensure_image(signer: Optional[dict]) -> Optional[str]:
    """Fetches the signature image when this signer version is not cached yet. Never raises: a missing signature must
    not stop a sync. Returns why the image is missing (shown to HRD), or None when it is there or not needed."""
    if not signer or not signer.get("ttd_versi") or signature_path(signer):
        return None
    sid, ver = str(signer.get("id") or ""), str(signer["ttd_versi"])
    if not (pdf_service._SAFE_ID.match(sid) and pdf_service._SAFE_ID.match(ver)):
        return "Data penandatangan dari ROSY tidak dikenali"
    try:
        got = await integrations.fetch_signer_image()
    except Exception as e:  # noqa: BLE001
        logger.warning("tanda tangan %s gagal diambil: %s", sid, e)
        return f"ROSY tidak dapat dihubungi ({e})"
    if got is None:
        return "ROSY tidak dapat menyediakan berkas tanda tangannya"
    data, sent = got
    if sent and sent != ver:  # the signature was replaced in ROSY between the two calls
        return "Tanda tangan di ROSY baru saja diganti; ambil ulang dari ROSY"
    try:
        _store(sid, ver, data)
    except Exception:  # noqa: BLE001
        logger.exception("berkas tanda tangan %s tidak terbaca", sid)
        return "Berkas tanda tangan dari ROSY bukan gambar yang dapat dibaca"
    return None


async def remember(signer: Optional[dict], company: Optional[dict], error: Optional[str]) -> None:
    """The signer last seen in ROSY, shown on the Config page."""
    await db.slip_signer.update_one({"id": "current"}, {"$set": {
        "signer": signer, "company": company, "error": error, "fetched_at": now_iso()}}, upsert=True)


async def refresh() -> dict:
    """'Ambil dari ROSY' on the Config page: the current signer and image, applied at once to every period that is not
    fully approved, so the preview and the next approval show it without a full sync. Slips already approved keep
    their PDF, signed as it was."""
    signer, company = await integrations.fetch_signer()
    error = await ensure_image(signer)
    await remember(signer, company, error)
    await db.payroll_periods.update_many({"status": {"$ne": "approved"}}, {"$set": {"signer": signer}})
    return await current()


async def current() -> dict:
    doc = await db.slip_signer.find_one({"id": "current"}, {"_id": 0})
    if not doc:  # nothing fetched since this feature: the newest synced period knows the signer
        p = await db.payroll_periods.find_one({"signer": {"$exists": True}},
                                              {"_id": 0, "signer": 1, "company": 1, "employees_synced_at": 1},
                                              sort=[("start_date", -1)]) or {}
        doc = {"signer": p.get("signer"), "company": p.get("company"), "fetched_at": p.get("employees_synced_at"),
               "error": None}
    signer = doc.get("signer")
    path = signature_path(signer)
    image = ("data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()) if path else None
    return {**doc, "status": status(signer), "source": integrations.mode("ROSY"), "image": image}
