"""Slip signer (penandatangan) from ROSY: HAM's payroll Document Signer — name and position.

ROSY stays the one place to manage signers (HRD: Penandatangan Dokumen); RASA shows them and prints them under the QR
code of the slip. Since 14 Oct 2026 the slip is "signed" with that QR (verify.py), not with the signature image, so the
image is no longer fetched; the signer's name and position are all RASA needs (user request 14 Oct 2026)."""
from typing import Optional

from core import db, now_iso, get_configs
import integrations
import verify


def status(signer: Optional[dict]) -> str:
    """tanpa_penandatangan | ada"""
    return "ada" if signer and signer.get("nama") else "tanpa_penandatangan"


async def remember(signer: Optional[dict], company: Optional[dict]) -> None:
    """The signer last seen in ROSY, shown on the Config page."""
    await db.slip_signer.update_one({"id": "current"}, {"$set": {
        "signer": signer, "company": company, "fetched_at": now_iso()}}, upsert=True)


async def refresh() -> dict:
    """'Ambil dari ROSY' on the Config page: the current signer, applied at once to every period that is not fully
    approved, so the preview and the next approval show it without a full sync. Slips already approved keep their PDF,
    signed as it was."""
    signer, company = await integrations.fetch_signer()
    await remember(signer, company)
    await db.payroll_periods.update_many({"status": {"$ne": "approved"}}, {"$set": {"signer": signer}})
    return await current()


async def current() -> dict:
    doc = await db.slip_signer.find_one({"id": "current"}, {"_id": 0})
    if not doc:  # nothing fetched since this feature: the newest synced period knows the signer
        p = await db.payroll_periods.find_one({"signer": {"$exists": True}},
                                              {"_id": 0, "signer": 1, "company": 1, "employees_synced_at": 1},
                                              sort=[("start_date", -1)]) or {}
        doc = {"signer": p.get("signer"), "company": p.get("company"), "fetched_at": p.get("employees_synced_at")}
    base = verify.base_url(await get_configs())
    # verify_base = where the QR on the slips points (the Config page warns when only this computer can open it)
    return {**doc, "status": status(doc.get("signer")), "source": integrations.mode("ROSY"),
            "verify_base": base, "verify_base_local": bool(base) and verify.is_local(base)}
