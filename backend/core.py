import os
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import HTTPException, Request, Depends
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

JWT_ALGORITHM = "HS256"
HR_ROLES = ("manager_hrd", "supervisor")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_access_token(user_id: str, role: str) -> str:
    payload = {"sub": user_id, "role": role, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def require_hr(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Akses khusus Manager HRD / Supervisor HRD")
    return user


async def require_manager(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "manager_hrd":
        raise HTTPException(403, "Hanya Manager HRD yang dapat melakukan aksi ini")
    return user


def actor(user: dict) -> str:
    """Audit identity: the ROSY username (RUSA users have no email)."""
    return user.get("username") or user["id"]


def csv_delimiter(cfg: dict) -> str:
    d = cfg.get("CSV_DELIMITER", ",")
    return "\t" if d.lower() == "tab" else d


DEFAULT_CONFIGS = {
    "UMK_BEKASI_REGENCY": ("5219263", "UMK Kabupaten Bekasi (floor basis BPJS Kesehatan)"),
    "BPJS_JP_MAX_WAGE": ("10042300", "Plafon upah maksimal Jaminan Pensiun"),
    "BPJS_KES_MAX_WAGE": ("12000000", "Plafon upah maksimal BPJS Kesehatan"),
    "DEFAULT_WORK_DAYS": ("25", "Standar hari kerja bulanan (PP 35/2021)"),
    "PPH21_BASIS": ("bersih", "Dasar PPh 21: bersih = sesudah Potongan Presensi & Absensi, kotor = sebelum potongan itu"),
    "COMPANY_NAME": ("[NAMA_PERUSAHAAN]", "Nama pemotong pajak (1721-A1)"),
    "COMPANY_ADDRESS": ("[ALAMAT_PERUSAHAAN]", "Alamat perusahaan (1721-A1; kop slip gaji memakai logo RPI & RUMAT)"),
    "CSV_DELIMITER": (",", "Pemisah kolom ekspor CSV: , atau ; atau | atau tab"),
    "COMPANY_NPWP": ("[NPWP_PEMOTONG]", "NPWP pemotong pajak (1721-A1)"),
    "BSI_COMPANY_DEBIT_ACCOUNT": ("[ISI_REKENING_DEBET_PERUSAHAAN]", "No. rekening debet BSI perusahaan (ekspor transfer massal)"),
    "SLIP_VERIFY_BASE_URL": ("", "Alamat publik RUSA untuk QR verifikasi slip, mis. https://rusa.rumat.id (kosong = alamat frontend pertama di CORS_ORIGINS)"),
}

# configs that only accept a fixed set of values: validated on save and sent to the Config page as `choices`
CONFIG_CHOICES = {"PPH21_BASIS": ("bersih", "kotor")}


async def get_configs() -> dict:
    docs = await db.payroll_configs.find({}, {"_id": 0}).to_list(100)
    return {d["config_key"]: d["config_value"] for d in docs}
