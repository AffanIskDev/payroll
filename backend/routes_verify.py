"""Verifikasi slip untuk umum (user 14 Okt 2026) — satu-satunya rute RUSA tanpa login: siapa pun yang memindai QR di slip
mendapat jawabannya, jadi isinya hanya yang dikembalikan verify.lookup (tanpa nominal gaji, nama disamarkan)."""
from fastapi import APIRouter, HTTPException, Response

import verify

router = APIRouter(prefix="/api/verify")


@router.get("/{code}")
async def verify_slip(code: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    answer = await verify.lookup(code)
    if answer is None:
        raise HTTPException(404, "Slip tidak ditemukan")
    return answer
