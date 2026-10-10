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
from access import role_for  # noqa: E402
import integrations  # noqa: E402
import routes_hr  # noqa: E402
import routes_tax  # noqa: E402
import routes_recap  # noqa: E402

app = FastAPI(title="RASA")
auth = APIRouter(prefix="/api/auth")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class LoginIn(BaseModel):
    username: str
    password: str


@auth.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    """ROSY username + password, checked by HAM; access follows the ROSY position (access.role_for)."""
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
        acc = await integrations.verify_rosy_login(username, body.password, ip)
    except HTTPException as e:
        if e.status_code == 401:
            await db.login_attempts.update_one({"identifier": key}, {
                "$inc": {"count": 1}, "$set": {"locked_until": (now + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise
    await db.login_attempts.delete_one({"identifier": key})
    role = role_for(acc.get("jabatan"))
    fields = {"username": acc.get("username") or username, "name": acc.get("nama") or username, "role": role,
              "rosy_employee_id": acc.get("employee_id"), "jabatan": acc.get("jabatan") or [],
              "last_login_at": now_iso()}
    # Upsert even without access: a known user whose position no longer qualifies loses the role at once,
    # which also invalidates the tokens they still hold (get_current_user re-reads the role every request)
    await db.users.update_one({"rosy_user_id": acc["user_id"]}, {
        "$set": fields, "$setOnInsert": {"id": str(uuid.uuid4()), "rosy_user_id": acc["user_id"],
                                         "created_at": now_iso()}}, upsert=True)
    if not role:
        raise HTTPException(403, "Akun ROSY Anda tidak memiliki akses ke RASA. RASA khusus Manager HRD "
                                 "dan Supervisor HRD (sesuai jabatan di ROSY)")
    user = await db.users.find_one({"rosy_user_id": acc["user_id"]}, {"_id": 0})
    return _issue(user, response)


def _issue(user: dict, response: Response) -> dict:
    token = create_access_token(user["id"], user["role"])
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"token": token, "user": {k: user.get(k) for k in ("id", "username", "name", "role")}}


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
app.include_router(routes_hr.router)
app.include_router(routes_tax.router)
app.include_router(routes_recap.router)

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
