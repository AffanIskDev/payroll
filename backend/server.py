from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import os  # noqa: E402
import logging  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timezone, timedelta  # noqa: E402

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from core import (MASTER_ADMIN, akses_user, client, create_access_token, daftar_pt, db, get_current_user,  # noqa: E402
                  now_iso, pt_awal)
from seed import seed  # noqa: E402
import accounts  # noqa: E402
import integrations  # noqa: E402
import routes_hr  # noqa: E402
import gaji_rusa  # noqa: E402
import tambahan_rusa  # noqa: E402
import special_runs  # noqa: E402
import routes_tax  # noqa: E402
import export_data  # noqa: E402
import routes_bpjs_tk  # noqa: E402
import routes_recap  # noqa: E402
import routes_verify  # noqa: E402

app = FastAPI(title="RUSA")
auth = APIRouter(prefix="/api/auth")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class LoginIn(BaseModel):
    username: str
    password: str


class PtIn(BaseModel):
    company_id: str


@auth.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    """Akun RUSA sendiri (accounts.py): peran & akses dari daftar pengguna RUSA; kata sandi menurut sumbernya (RUSA / ROSY)."""
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(400, "Username dan password wajib diisi")
    ip = request.client.host if request.client else ""
    key = f"{ip or 'x'}:{username.lower()}"
    attempt = await db.login_attempts.find_one({"identifier": key})
    now = datetime.now(timezone.utc)
    if attempt and attempt.get("count", 0) >= 5 and attempt.get("locked_until", "") > now.isoformat():
        raise HTTPException(429, "Terlalu banyak percobaan login. Coba lagi dalam 15 menit")
    try:
        user = await accounts.authenticate(username, body.password, ip)
    except HTTPException as e:
        if e.status_code == 401:
            await db.login_attempts.update_one({"identifier": key}, {
                "$inc": {"count": 1}, "$set": {"locked_until": (now + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise
    await db.login_attempts.delete_one({"identifier": key})
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login_at": now_iso()}})
    akses = await akses_user(user)
    return await _issue(user, response, pt_awal(user, akses), akses)


async def _issue(user: dict, response: Response, pt=None, akses=None) -> dict:
    """Token sesi. Pengguna HR: berlaku untuk SATU PT aktif (`pt`) dengan perannya di PT itu; Master Admin: tanpa PT."""
    akses = akses or {}
    role = user["role"] if user.get("role") == MASTER_ADMIN else akses.get(pt, user.get("role"))
    token = create_access_token(user["id"], role, pt)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    out = {k: user.get(k) for k in ("id", "username", "name", "akun_uji", "must_change_password")}
    return {"token": token, "user": {**out, "role": role, **await _pt_info(pt, akses)}}


async def _pt_info(pt, akses: dict) -> dict:
    """PT aktif + daftar PT yang boleh dibuka (untuk pilihan PT di sidebar)."""
    nama = {c["id"]: c for c in await daftar_pt()}
    daftar = [{"id": i, "nama": nama[i].get("nama"), "nama_legal": nama[i].get("nama_legal"), "role": r}
              for i, r in sorted(akses.items()) if i in nama]
    aktif = next((d for d in daftar if d["id"] == pt), None)
    return {"pt": aktif, "daftar_pt": daftar}


@auth.post("/pt")
async def ganti_pt(body: PtIn, response: Response, user: dict = Depends(get_current_user)):
    """Ganti PT aktif (pilihan PT di sidebar): token baru untuk PT itu bila pengguna punya akses ke sana. PT terakhir
    dicatat (pt_terakhir), tetapi login tetap membuka RUMAT dulu (core.pt_awal, user 7 Nov 2026)."""
    if user.get("role") == MASTER_ADMIN:
        raise HTTPException(403, "Master Admin tidak membuka data gaji perusahaan")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    akses = await akses_user(u)
    if body.company_id not in akses:
        raise HTTPException(403, "Anda tidak punya akses ke perusahaan ini")
    await db.users.update_one({"id": u["id"]}, {"$set": {"pt_terakhir": body.company_id}})
    return await _issue(u, response, body.company_id, akses)


@auth.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@auth.get("/me")
async def me(user: dict = Depends(get_current_user)):
    if user.get("role") == MASTER_ADMIN:
        return {**user, "pt": None, "daftar_pt": []}
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return {**user, **await _pt_info(user.get("pt"), await akses_user(u))}


@app.get("/api/health")
async def health():
    return {"ok": True}


app.include_router(auth)
app.include_router(accounts.auth_router)  # ganti kata sandi (akun RUSA)
app.include_router(accounts.router)  # daftar pengguna RUSA (Manager)
app.include_router(routes_hr.router)
app.include_router(gaji_rusa.router)  # gaji diinput di RUSA per PT (18 Nov 2026)
app.include_router(tambahan_rusa.router)  # Tambahan Bulanan diinput di RUSA (18 Nov 2026)
app.include_router(special_runs.router)  # THR & Bonus Tahunan (30 Okt 2026)
app.include_router(routes_tax.router)
app.include_router(export_data.router)  # Export Data Payroll (Excel), Manager HRD — 3 Nov 2026
app.include_router(routes_bpjs_tk.router)
app.include_router(routes_recap.router)
app.include_router(routes_verify.router)  # tanpa login: dibuka dari QR di slip (user 14 Okt 2026)

# Real ROSY accounts log in here: limit cross-origin credentialed calls to the frontend origin(s)
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if not _origins:
    logging.getLogger("server").warning("CORS_ORIGINS belum diatur: semua origin diizinkan")
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=_origins,
                   allow_origin_regex=None if _origins else ".*", allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Exported-Count", "X-Skipped-Niks", "X-Total-Amount"])


@app.on_event("startup")
async def startup():
    await seed()


@app.on_event("shutdown")
async def shutdown():
    client.close()
