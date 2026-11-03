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

from core import db, client, now_iso, create_access_token, get_current_user  # noqa: E402
from seed import seed  # noqa: E402
import accounts  # noqa: E402
import integrations  # noqa: E402
import routes_hr  # noqa: E402
import routes_tax  # noqa: E402
import export_data  # noqa: E402
import employees_rusa  # noqa: E402
import routes_bpjs_tk  # noqa: E402
import routes_recap  # noqa: E402
import routes_verify  # noqa: E402

app = FastAPI(title="RUSA")
auth = APIRouter(prefix="/api/auth")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class LoginIn(BaseModel):
    username: str
    password: str


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
    return _issue(user, response)


def _issue(user: dict, response: Response) -> dict:
    token = create_access_token(user["id"], user["role"])
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"token": token, "user": {k: user.get(k) for k in ("id", "username", "name", "role", "akun_uji", "must_change_password")}}


@auth.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@auth.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@app.get("/api/health")
async def health():
    return {"ok": True}


app.include_router(auth)
app.include_router(accounts.auth_router)  # ganti kata sandi (akun RUSA)
app.include_router(accounts.router)  # daftar pengguna RUSA (Manager)
app.include_router(routes_hr.router)
app.include_router(routes_tax.router)
app.include_router(employees_rusa.router)  # karyawan & gaji yang diinput di RUSA — 3 Nov 2026
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
