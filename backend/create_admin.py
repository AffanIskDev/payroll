"""Membuat Manager HRD PERTAMA (atau menambah pengguna dari server) tanpa lewat layar — sekali jalan di server RUSA.

  cd /var/www/rusa/backend && sudo -u rusa .venv/bin/python create_admin.py <username> "<Nama Lengkap>" [--rosy] [--role supervisor]

Tanpa --rosy: kata sandi diminta di terminal (tak tampil, tak masuk riwayat); karena pembuatnya sendiri yang memilihnya,
tidak dipaksa ganti di login pertama.
Dengan --rosy: memakai kata sandi ROSY (perlu HAM; username harus sama dengan username ROSY)."""
import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import accounts  # noqa: E402
from core import current_company, db  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("name")
    ap.add_argument("--rosy", action="store_true", help="kata sandi memakai ROSY (bukan kata sandi RUSA)")
    ap.add_argument("--role", default="manager_hrd", choices=accounts.ROLES)
    a = ap.parse_args()
    password = None
    if not a.rosy:
        password = getpass.getpass("Kata sandi: ")
        if password != getpass.getpass("Ulangi kata sandi: "):
            print("Kata sandi tidak sama"); return 1
        if problem := accounts.password_problem(password, a.username):
            print(problem); return 1
    await accounts.migrate_users()
    user, _ = await accounts.create_user(a.username, a.name, a.role, "rosy" if a.rosy else "local", "skrip:create_admin", password)
    if not a.rosy:   # sandi dipilih sendiri oleh pembuatnya
        await db.users.update_one({"id": user["id"]}, {"$set": {"must_change_password": False}})
    print(f"OK: {user['username']} ({user['role']}) untuk {current_company()} — {'ROSY' if a.rosy else 'kata sandi RUSA'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:  # noqa: BLE001
        print("Gagal:", getattr(e, "detail", e)); sys.exit(1)
