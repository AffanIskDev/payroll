import contextvars
import os
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import HTTPException, Request, Depends
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])

JWT_ALGORITHM = "HS256"
HR_ROLES = ("manager_hrd", "supervisor")
# Master Admin (3 Nov 2026): HANYA mengatur pengguna & akses RUSA (accounts.py), tanpa akses data gaji — pemisahan tugas:
# yang menunjuk siapa boleh memakai RUSA bukan orang yang menyetujui gaji
MASTER_ADMIN = "master_admin"

# ------------------------------------------------------------------ multi-PT (6 Nov 2026)
# Satu RUSA melayani beberapa PT (RUMAT, Botanova, RUMI, RKM, …) di SATU database: setiap dokumen data gaji membawa
# `company_id`, dan PT aktif datang dari SESI (klaim `pt` di token), bukan dari .env per instance. Penyaringan dipusatkan
# di `db` di bawah: koleksi data gaji otomatis disaring & diisi `company_id` PT aktif, jadi kode rute tidak perlu (dan
# tidak bisa lupa) menyaring sendiri. Tanpa konteks PT, akses ke koleksi itu DITOLAK — bukan diam-diam membaca semua PT.

# Koleksi milik seluruh RUSA (bukan per PT). Semua koleksi lain = data per PT.
GLOBAL_COLLECTIONS = {"users", "login_attempts", "access_log", "companies"}

_PT = contextvars.ContextVar("rusa_pt", default=None)
_SEMUA_PT = contextvars.ContextVar("rusa_semua_pt", default=False)


class TanpaKonteksPT(RuntimeError):
    """Kode menyentuh data per PT tanpa PT aktif (bug, bukan keadaan pengguna)."""


def env_company() -> str:
    """PT dari .env — HANYA untuk memberi `company_id` pada data lama satu-PT saat migrasi; bukan PT aktif request."""
    return os.environ.get("PAYROLL_COMPANY_ID", "CP-001")


def current_company() -> str:
    """PT aktif request/tugas ini (dipasang get_current_user dari token, atau dengan_pt() di skrip/migrasi/tes)."""
    pt = _PT.get()
    if not pt:
        raise TanpaKonteksPT("Tidak ada PT aktif")
    return pt


def ada_pt() -> bool:
    return bool(_PT.get())


@contextmanager
def dengan_pt(pt: str):
    """Jalankan blok kode sebagai PT `pt` (migrasi, seed, skrip, tes)."""
    tok = _PT.set(pt)
    try:
        yield
    finally:
        _PT.reset(tok)


@contextmanager
def semua_pt():
    """Lintas PT tanpa saringan — HANYA untuk migrasi startup dan halaman verifikasi QR publik."""
    tok = _SEMUA_PT.set(True)
    try:
        yield
    finally:
        _SEMUA_PT.reset(tok)


class _KoleksiPT:
    """Koleksi Motor yang setiap filternya ditambah `company_id` PT aktif dan setiap dokumen barunya diberi `company_id`."""

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name):  # index_information, create_index, drop_index, name, …
        return getattr(self._raw, name)

    @staticmethod
    def _saring(filt):
        pt = current_company()
        f = dict(filt or {})
        if f.get("company_id", pt) != pt:
            raise TanpaKonteksPT(f"Filter meminta PT {f['company_id']} di dalam sesi PT {pt}")
        f["company_id"] = pt
        return f

    def _arg(self, a, k):
        if "filter" in k:
            k["filter"] = self._saring(k["filter"])
            return a, k
        return ((self._saring(a[0]),) + tuple(a[1:])) if a else (self._saring({}),), k

    def find(self, *a, **k):
        a, k = self._arg(a, k)
        return self._raw.find(*a, **k)

    def aggregate(self, pipeline, *a, **k):
        return self._raw.aggregate([{"$match": {"company_id": current_company()}}] + list(pipeline), *a, **k)

    def distinct(self, key, filter=None, *a, **k):
        return self._raw.distinct(key, self._saring(filter), *a, **k)

    async def insert_one(self, doc, *a, **k):
        doc["company_id"] = current_company()
        return await self._raw.insert_one(doc, *a, **k)

    async def insert_many(self, docs, *a, **k):
        pt = current_company()
        docs = list(docs)
        for d in docs:
            d["company_id"] = pt
        return await self._raw.insert_many(docs, *a, **k)

    async def replace_one(self, filt, replacement, *a, **k):
        replacement["company_id"] = current_company()
        return await self._raw.replace_one(self._saring(filt), replacement, *a, **k)

    async def bulk_write(self, *a, **k):
        raise TanpaKonteksPT("bulk_write belum disaring per PT — pakai update/insert biasa")


def _pembungkus(nama):
    async def metode(self, *a, **k):
        a, k = self._arg(a, k)
        return await getattr(self._raw, nama)(*a, **k)
    metode.__name__ = nama
    return metode


for _m in ("find_one", "update_one", "update_many", "delete_one", "delete_many", "count_documents",
           "find_one_and_update", "find_one_and_delete", "find_one_and_replace"):
    setattr(_KoleksiPT, _m, _pembungkus(_m))


class _DbPT:
    """Pengganti `client[DB_NAME]`: koleksi GLOBAL_COLLECTIONS apa adanya, koleksi lain tersaring PT aktif."""

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        coll = self._raw[name]
        return coll if name in GLOBAL_COLLECTIONS or _SEMUA_PT.get() else _KoleksiPT(coll)

    def __getitem__(self, name):
        return self.__getattr__(name)

    async def list_collection_names(self, *a, **k):
        return await self._raw.list_collection_names(*a, **k)


raw_db = client[os.environ["DB_NAME"]]
db = _DbPT(raw_db)

# Nama PT bawaan (sama dengan mt_company ROSY); daftar ini hanya mengisi koleksi `companies` bila belum ada.
DEFAULT_COMPANIES = [
    {"id": "CP-001", "nama": "RUMAT", "nama_legal": "PT Rumah Perawatan Indonesia"},
    {"id": "CP-002", "nama": "Botanova", "nama_legal": "Botanova RUMAT Holding"},
    {"id": "CP-003", "nama": "RUMI", "nama_legal": "Rumat Mahir Indonesia"},
    {"id": "CP-005", "nama": "RKM", "nama_legal": "Klinik Pratama RUMAT"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_access_token(user_id: str, role: str, pt: str = None) -> str:
    """`pt` = PT aktif sesi (tidak ada untuk Master Admin). Ganti PT = token baru (POST /api/auth/pt)."""
    payload = {"sub": user_id, "role": role, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    if pt:
        payload["pt"] = pt
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


async def daftar_pt(aktif_saja: bool = True) -> list:
    """PT yang dilayani RUSA (koleksi global `companies`), urut id."""
    q = {"is_active": {"$ne": False}} if aktif_saja else {}
    return await db.companies.find(q, {"_id": 0}).sort("id", 1).to_list(100)


async def akses_user(user: dict) -> dict:
    """{company_id: peran} pengguna HR. `semua_pt` = semua PT aktif (termasuk PT yang ditambahkan kemudian) dengan peran
    bawaannya; selain itu daftar `akses` [{company_id, role}]. Master Admin / nonaktif → {} (tanpa akses data gaji)."""
    if user.get("role") == MASTER_ADMIN or user.get("is_active") is False:
        return {}
    aktif = [c["id"] for c in await daftar_pt()]
    if user.get("semua_pt"):
        return {pt: user["role"] for pt in aktif} if user.get("role") in HR_ROLES else {}
    return {a["company_id"]: a["role"] for a in (user.get("akses") or [])
            if a.get("company_id") in aktif and a.get("role") in HR_ROLES}


def pt_awal(user: dict, akses: dict):
    """PT yang dibuka saat login: PT terakhir dipakai, lalu PT utama, lalu yang pertama menurut urutan id."""
    for pt in (user.get("pt_terakhir"), user.get("pt_utama")):
        if pt in akses:
            return pt
    return sorted(akses)[0] if akses else None


async def get_current_user(request: Request) -> dict:
    """Pengguna sesi + PT aktifnya. Peran pengguna HR = perannya DI PT AKTIF (akses per PT), dibaca ulang setiap request:
    akses yang dicabut / dinonaktifkan berlaku seketika. Memasang PT aktif sebagai konteks `db` untuk sisa request."""
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
    if user.get("is_active") is False:
        raise HTTPException(401, "Akses Anda ke RUSA sudah dinonaktifkan")
    if user.get("role") == MASTER_ADMIN:
        return user   # tanpa PT aktif: Master Admin tidak menyentuh data gaji
    akses = await akses_user(user)
    pt = payload.get("pt")
    if not pt or pt not in akses:
        raise HTTPException(401, "Akses Anda ke perusahaan ini sudah dicabut. Silakan masuk kembali")
    _PT.set(pt)
    return {**user, "role": akses[pt], "pt": pt}


def _password_gate(user: dict) -> dict:
    # kata sandi sementara dari Manager: tak bisa memakai fitur apa pun sebelum diganti (hanya /auth/me & /auth/change-password)
    if user.get("must_change_password"):
        raise HTTPException(403, "Ganti kata sandi sementara Anda dulu")
    return user


async def require_hr(user: dict = Depends(get_current_user)) -> dict:
    _password_gate(user)
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "Akses khusus Manager HRD / Supervisor HRD")
    return user


async def require_master_admin(user: dict = Depends(get_current_user)) -> dict:
    _password_gate(user)
    if user.get("role") != MASTER_ADMIN:
        raise HTTPException(403, "Hanya Master Admin yang dapat mengatur pengguna RUSA")
    return user


async def require_manager(user: dict = Depends(get_current_user)) -> dict:
    _password_gate(user)
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
    "UMK_BEKASI_REGENCY": ("5219263", "UMK lokasi perusahaan ini (dasar BPJS Kesehatan flat UMK & batas bawah) — isi sesuai kota/kabupaten PT"),
    "BPJS_JP_MAX_WAGE": ("10042300", "Plafon upah maksimal Jaminan Pensiun"),
    "BPJS_KES_MAX_WAGE": ("12000000", "Plafon upah maksimal BPJS Kesehatan"),
    "DEFAULT_WORK_DAYS": ("25", "Standar hari kerja bulanan (PP 35/2021)"),
    "BPJS_KES_BASIS": ("flat_umk", "Dasar BPJS Kesehatan: flat_umk = semua karyawan memakai nilai UMK, formula = yang terbesar antara gaji pokok dan UMK (maks. plafon)"),
    "BPJS_TK_BASIS": ("formula", "Dasar BPJS Ketenagakerjaan: import = JKK/JKM/JHT/JP memakai data given dari BPJS (diimpor di halaman Konfigurasi), formula = dihitung dari gaji pokok; karyawan tanpa data given tetap memakai rumus"),
    "PPH21_BASIS": ("bersih", "Dasar PPh 21: bersih = sesudah Potongan Presensi & Absensi, kotor = sebelum potongan itu"),
    "COMPANY_NAME": ("[NAMA_PERUSAHAAN]", "Cadangan nama pemotong 1721-A1 — dipakai hanya bila nama legal di ROSY (Master Perusahaan) kosong"),
    "COMPANY_ADDRESS": ("[ALAMAT_PERUSAHAAN]", "Cadangan alamat 1721-A1 — dipakai hanya bila alamat di ROSY (Master Perusahaan) kosong"),
    "CSV_DELIMITER": (",", "Pemisah kolom ekspor CSV: , atau ; atau | atau tab"),
    "COMPANY_NPWP": ("[NPWP_PEMOTONG]", "Cadangan NPWP pemotong 1721-A1 — dipakai hanya bila NPWP di ROSY (Master Perusahaan) kosong"),
    "BSI_COMPANY_DEBIT_ACCOUNT": ("[ISI_REKENING_DEBET_PERUSAHAAN]", "No. rekening debet BSI perusahaan (ekspor transfer massal)"),
    "SLIP_VERIFY_BASE_URL": ("", "Alamat publik RUSA untuk QR verifikasi slip, mis. https://rusa.rumat.id (kosong = alamat frontend pertama di CORS_ORIGINS)"),
}

# configs that only accept a fixed set of values: validated on save and sent to the Config page as `choices`
CONFIG_CHOICES = {"PPH21_BASIS": ("bersih", "kotor"), "BPJS_KES_BASIS": ("flat_umk", "formula"),
                  "BPJS_TK_BASIS": ("import", "formula")}


async def get_configs() -> dict:
    docs = await db.payroll_configs.find({}, {"_id": 0}).to_list(100)
    return {d["config_key"]: d["config_value"] for d in docs}
