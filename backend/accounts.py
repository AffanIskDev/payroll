"""Akun & hak akses RUSA sendiri (user 3 Nov 2026) — terpisah dari ROSY.

ROSY khusus karyawan RUMAT, sedangkan RUSA dipakai beberapa perusahaan; siapa boleh memakai RUSA dan sebagai apa diatur di
SINI (Manager HRD menunjuk orangnya), bukan ditebak dari jabatan di ROSY. Tiap pengguna:
  username, name, role (manager_hrd | supervisor), is_active, companies [id perusahaan yang boleh diakses],
  auth_mode: "local"  = kata sandi disimpan di RUSA (bcrypt), wajib diganti saat login pertama bila dibuatkan Manager
             "rosy"   = kata sandi ROSY, diperiksa HAM (hanya verifikasi; HAM tak menulis apa pun)
Satu instance RUSA = satu perusahaan (PAYROLL_COMPANY_ID); daftar `companies` disimpan supaya bila nanti satu aplikasi dipakai
beberapa perusahaan, bentuk datanya sudah siap."""
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Body, Depends, HTTPException

from core import HR_ROLES, actor, current_company, db, get_current_user, now_iso, require_manager
import integrations

ROLES = ("manager_hrd", "supervisor")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
MIN_PASSWORD = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GENERIC_FAIL = "Username atau kata sandi salah"
# hash tiruan: lama respons sama saat username tak ada / nonaktif (tak membocorkan siapa yang terdaftar)
_DUMMY_HASH = bcrypt.hashpw(b"tidak-dipakai", bcrypt.gensalt(rounds=12))


# ------------------------------------------------------------------ kata sandi
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def check_password(pw: str, hashed: Optional[str]) -> bool:
    h = hashed.encode() if hashed else _DUMMY_HASH
    ok = bcrypt.checkpw((pw or "").encode("utf-8")[:72], h)
    return ok and bool(hashed)


def password_problem(pw: str, username: str = "") -> Optional[str]:
    if len(pw or "") < MIN_PASSWORD:
        return f"Kata sandi minimal {MIN_PASSWORD} karakter"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Kata sandi harus memuat huruf dan angka"
    if username and pw.lower() == username.lower():
        return "Kata sandi tidak boleh sama dengan username"
    return None


def generate_password() -> str:
    while True:
        pw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
        if re.search(r"\d", pw) and re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw):
            return pw


# ------------------------------------------------------------------ dokumen pengguna
def public(u: dict) -> dict:
    return {k: v for k, v in u.items() if k not in ("password_hash", "_id")}


async def create_user(username: str, name: str, role: str, auth_mode: str, by: str, password: Optional[str] = None) -> tuple:
    """Membuat pengguna. Mengembalikan (dokumen, kata sandi sementara | None). Raise HTTPException bila tak sah."""
    username = (username or "").strip()
    name = (name or "").strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(422, "Username 3–40 karakter: huruf, angka, titik, garis bawah, atau strip")
    if not name:
        raise HTTPException(422, "Nama wajib diisi")
    if role not in ROLES:
        raise HTTPException(422, "Peran harus Manager HRD atau Supervisor HRD")
    if auth_mode not in ("local", "rosy"):
        raise HTTPException(422, "Sumber kata sandi harus RUSA atau ROSY")
    if auth_mode == "rosy" and not rosy_available():
        raise HTTPException(422, "Perusahaan ini tidak terhubung ke ROSY; pakai kata sandi RUSA")
    if await db.users.find_one({"username_lower": username.lower()}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "Username sudah dipakai")
    temp = None
    doc = {"id": str(uuid.uuid4()), "username": username, "username_lower": username.lower(), "name": name, "role": role,
           "is_active": True, "auth_mode": auth_mode, "companies": [current_company()], "access_v2": True,
           "created_at": now_iso(), "created_by": by}
    if auth_mode == "local":
        pw = password or generate_password()
        if password and (problem := password_problem(password, username)):
            raise HTTPException(422, problem)
        temp = pw
        doc.update(password_hash=hash_password(pw), must_change_password=True)
    await db.users.insert_one({**doc})
    return public(doc), temp


def rosy_available() -> bool:
    return integrations.rosy_enabled() and integrations.mode("ROSY") == "live"


# ------------------------------------------------------------------ login
async def authenticate(username: str, password: str, ip: str) -> dict:
    """Memeriksa username + kata sandi menurut sumber kata sandi pengguna. Mengembalikan dokumen pengguna.
    Gagal = 401 dengan pesan SAMA untuk username tak dikenal / nonaktif / sandi salah; 403 bila sandi benar tapi
    pengguna tak punya akses ke perusahaan ini."""
    u = await db.users.find_one({"username_lower": username.strip().lower()}, {"_id": 0})
    usable = bool(u and u.get("is_active") and u.get("role") in HR_ROLES)
    if usable and u.get("auth_mode") == "rosy":
        try:
            acc = await integrations.verify_rosy_login(username, password, ip, credentials_only=True)
        except HTTPException as e:
            if e.status_code == 401:
                raise HTTPException(401, GENERIC_FAIL)
            raise
        if u.get("rosy_user_id") != acc.get("user_id"):
            await db.users.update_one({"id": u["id"]}, {"$set": {"rosy_user_id": acc.get("user_id")}})
            u["rosy_user_id"] = acc.get("user_id")
    else:
        ok = check_password(password, u.get("password_hash") if usable and u.get("auth_mode") == "local" else None)
        if not (usable and ok):
            raise HTTPException(401, GENERIC_FAIL)
    if current_company() not in (u.get("companies") or []):
        raise HTTPException(403, "Akun Anda tidak punya akses ke perusahaan ini")
    return u


# ------------------------------------------------------------------ migrasi
async def migrate_users():
    """Akun RUSA sendiri (3 Nov 2026). Akun yang dulu dibuat otomatis dari login ROSY (peran dari jabatan) dipindah ke daftar
    pengguna RUSA sekali jalan: sumber kata sandi ROSY, aktif bila waktu itu punya peran, akses ke perusahaan instance ini.
    Sesudahnya peran HANYA dibaca dari daftar ini."""
    if "email_1" in await db.users.index_information():
        await db.users.drop_index("email_1")
    async for u in db.users.find({"access_v2": {"$ne": True}}, {"_id": 0}):
        await db.users.update_one({"id": u["id"]}, {"$set": {
            "username_lower": (u.get("username") or "").lower(), "auth_mode": "rosy" if u.get("rosy_user_id") else "local",
            "is_active": u.get("role") in HR_ROLES, "companies": [current_company()], "access_v2": True}})
    await db.users.create_index("id", unique=True)
    await db.users.create_index("rosy_user_id", unique=True, name="rosy_user_id_unique",
                                partialFilterExpression={"rosy_user_id": {"$type": "string"}})
    await db.users.create_index("username_lower", unique=True, name="username_lower_unique",
                                partialFilterExpression={"username_lower": {"$type": "string"}})


# ------------------------------------------------------------------ endpoint
router = APIRouter(prefix="/api/hr", dependencies=[Depends(require_manager)])
auth_router = APIRouter(prefix="/api/auth")


async def _managers_left(excluding_id: str) -> int:
    return await db.users.count_documents({"id": {"$ne": excluding_id}, "role": "manager_hrd", "is_active": True,
                                           "companies": current_company()})


async def _log(by: str, action: str, target: dict, detail: Optional[dict] = None):
    await db.access_log.insert_one({"id": str(uuid.uuid4()), "at": now_iso(), "by": by, "action": action,
                                    "target_id": target["id"], "target_username": target["username"], "detail": detail or {}})


@router.get("/users")
async def list_users():
    users = await db.users.find({"companies": current_company()}, {"_id": 0, "password_hash": 0}).sort("username_lower", 1).to_list(500)
    return {"users": users, "company": current_company(), "rosy_available": rosy_available()}


@router.post("/users")
async def add_user(body: dict = Body(...), me: dict = Depends(require_manager)):
    u, temp = await create_user(body.get("username"), body.get("name"), body.get("role"), body.get("auth_mode") or "local",
                                actor(me), body.get("password") or None)
    await _log(actor(me), "tambah", u, {"role": u["role"], "auth_mode": u["auth_mode"]})
    return {"user": u, "temp_password": temp}


@router.put("/users/{uid}")
async def edit_user(uid: str, body: dict = Body(...), me: dict = Depends(require_manager)):
    u = await db.users.find_one({"id": uid, "companies": current_company()}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Pengguna tidak ditemukan")
    upd, temp = {}, None
    if "name" in body:
        if not str(body["name"]).strip():
            raise HTTPException(422, "Nama wajib diisi")
        upd["name"] = str(body["name"]).strip()
    if "role" in body:
        if body["role"] not in ROLES:
            raise HTTPException(422, "Peran harus Manager HRD atau Supervisor HRD")
        upd["role"] = body["role"]
    if "is_active" in body:
        upd["is_active"] = bool(body["is_active"])
    if "auth_mode" in body and body["auth_mode"] != u.get("auth_mode"):
        if body["auth_mode"] == "rosy" and not rosy_available():
            raise HTTPException(422, "Perusahaan ini tidak terhubung ke ROSY; pakai kata sandi RUSA")
        if body["auth_mode"] not in ("local", "rosy"):
            raise HTTPException(422, "Sumber kata sandi harus RUSA atau ROSY")
        upd["auth_mode"] = body["auth_mode"]
        if body["auth_mode"] == "local":
            temp = generate_password()
            upd.update(password_hash=hash_password(temp), must_change_password=True)
        else:
            upd["password_hash"] = None
            upd["must_change_password"] = False
    # jangan sampai tak ada Manager aktif, dan jangan mengunci diri sendiri
    losing_manager = (upd.get("role", u["role"]) != "manager_hrd") or (upd.get("is_active", u.get("is_active")) is False)
    if u["role"] == "manager_hrd" and u.get("is_active") and losing_manager and await _managers_left(uid) == 0:
        raise HTTPException(409, "Harus ada minimal satu Manager HRD aktif")
    if uid == me["id"] and (upd.get("is_active") is False or ("role" in upd and upd["role"] != u["role"])):
        raise HTTPException(409, "Anda tidak bisa menonaktifkan atau mengubah peran akun Anda sendiri")
    if not upd:
        return {"user": public(u), "temp_password": None}
    await db.users.update_one({"id": uid}, {"$set": {**upd, "updated_at": now_iso(), "updated_by": actor(me)}})
    new = await db.users.find_one({"id": uid}, {"_id": 0})
    await _log(actor(me), "ubah", new, {k: v for k, v in upd.items() if k not in ("password_hash",)})
    return {"user": public(new), "temp_password": temp}


@router.post("/users/{uid}/reset-password")
async def reset_password(uid: str, me: dict = Depends(require_manager)):
    u = await db.users.find_one({"id": uid, "companies": current_company()}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Pengguna tidak ditemukan")
    if u.get("auth_mode") != "local":
        raise HTTPException(409, "Pengguna ini memakai kata sandi ROSY; atur ulang di ROSY")
    temp = generate_password()
    await db.users.update_one({"id": uid}, {"$set": {"password_hash": hash_password(temp), "must_change_password": True,
                                                    "updated_at": now_iso(), "updated_by": actor(me)}})
    await _log(actor(me), "reset-password", u)
    return {"temp_password": temp}


@auth_router.post("/change-password")
async def change_password(body: dict = Body(...), user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if u.get("auth_mode") != "local":
        raise HTTPException(409, "Akun ini memakai kata sandi ROSY; ganti di ROSY")
    if not check_password(body.get("current_password") or "", u.get("password_hash")):
        raise HTTPException(400, "Kata sandi saat ini salah")
    new = body.get("new_password") or ""
    if new == body.get("current_password"):
        raise HTTPException(422, "Kata sandi baru harus berbeda dari yang lama")
    if problem := password_problem(new, u["username"]):
        raise HTTPException(422, problem)
    await db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": hash_password(new), "must_change_password": False,
                                                        "password_changed_at": now_iso()}})
    return {"ok": True}
