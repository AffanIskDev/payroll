from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import os  # noqa: E402
import logging  # noqa: E402
from datetime import datetime, timezone, timedelta  # noqa: E402

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from core import db, client, verify_password, create_access_token, get_current_user  # noqa: E402
from seed import seed  # noqa: E402
import routes_hr  # noqa: E402
import routes_employee  # noqa: E402
import routes_tax  # noqa: E402
import routes_recap  # noqa: E402

app = FastAPI(title="Payroll ROSY & Rumatku")
auth = APIRouter(prefix="/api/auth")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class LoginIn(BaseModel):
    identifier: str
    password: str


@auth.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    ident = body.identifier.strip()
    key = f"{request.client.host if request.client else 'x'}:{ident.lower()}"
    attempt = await db.login_attempts.find_one({"identifier": key})
    now = datetime.now(timezone.utc)
    if attempt and attempt.get("count", 0) >= 5 and attempt.get("locked_until", "") > now.isoformat():
        raise HTTPException(429, "Terlalu banyak percobaan login. Coba lagi dalam 15 menit")
    user = await db.users.find_one({"$or": [{"email": ident.lower()}, {"nik": ident.upper()}]})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": key}, {
            "$inc": {"count": 1}, "$set": {"locked_until": (now + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise HTTPException(401, "Email/NIK atau password salah")
    await db.login_attempts.delete_one({"identifier": key})
    return _issue(user, response)


DEMO_ACCOUNTS = {"hrd": "hrd.manager@rumatku.id", "staff": "staff.hr@rumatku.id", "budi": "budi@rumatku.id",
                 "siti": "siti@rumatku.id", "dimas": "dimas@rumatku.id"}


class DemoIn(BaseModel):
    account: str


def _issue(user: dict, response: Response) -> dict:
    token = create_access_token(user["id"], user["role"])
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"token": token, "user": {k: user.get(k) for k in ("id", "email", "name", "role", "nik", "employee_id")}}


@auth.get("/demo-enabled")
async def demo_enabled():
    return {"enabled": os.environ.get("DEMO_LOGIN_ENABLED") == "true"}


@auth.post("/demo-login")
async def demo_login(body: DemoIn, response: Response):
    if os.environ.get("DEMO_LOGIN_ENABLED") != "true" or body.account not in DEMO_ACCOUNTS:
        raise HTTPException(403, "Login tester tidak aktif")
    user = await db.users.find_one({"email": DEMO_ACCOUNTS[body.account]})
    if not user:
        raise HTTPException(404, "Akun tester tidak ditemukan")
    return _issue(user, response)


@auth.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@auth.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


app.include_router(auth)
app.include_router(routes_hr.router)
app.include_router(routes_employee.router)
app.include_router(routes_tax.router)
app.include_router(routes_recap.router)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origin_regex=".*",
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Exported-Count", "X-Skipped-Niks"])


@app.on_event("startup")
async def startup():
    await seed()


@app.on_event("shutdown")
async def shutdown():
    client.close()
