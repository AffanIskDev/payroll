"""Verifikasi slip untuk umum (user 14 Okt 2026) — satu-satunya rute RUSA tanpa login: siapa pun yang memindai QR di slip
mendapat jawabannya, jadi isinya hanya yang dikembalikan verify.lookup (tanpa nominal gaji, nama disamarkan)."""
from fastapi import APIRouter, HTTPException, Response

import verify
from core import semua_pt

router = APIRouter(prefix="/api/verify")


@router.get("/{code}")
async def verify_slip(code: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    # Tanpa login = tanpa PT aktif: kode QR unik di seluruh RUSA, jadi dicari lintas PT (multi-PT 6 Nov 2026)
    with semua_pt():
        answer = await verify.lookup(code)
    if answer is None:
        raise HTTPException(404, "Slip tidak ditemukan")
    return answer
