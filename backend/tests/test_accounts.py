"""Akun & hak akses RUSA sendiri (3 Nov 2026) — uji murni: tanpa server, tanpa database."""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")
os.environ.setdefault("JWT_SECRET", "uji")

import accounts as ac  # noqa: E402
import core  # noqa: E402


def test_hash_roundtrip_and_wrong_password():
    h = ac.hash_password("Rahasia12345")
    assert h != "Rahasia12345" and h.startswith("$2")
    assert ac.check_password("Rahasia12345", h)
    assert not ac.check_password("rahasia12345", h)
    assert not ac.check_password("apa saja", None)          # tak ada hash (user tak ada/ROSY) = selalu salah, tanpa error


@pytest.mark.parametrize("pw,needle", [("pendek1", "minimal"), ("hurufsajapanjang", "huruf dan angka"),
                                       ("1234567890123", "huruf dan angka"), ("Budi.Santoso1", "sama dengan username")])
def test_password_policy(pw, needle):
    assert needle in (ac.password_problem(pw, "budi.santoso1") or "")


def test_good_password_passes_and_generated_one_always_does():
    assert ac.password_problem("Rahasia12345", "budi") is None
    for _ in range(50):
        pw = ac.generate_password()
        assert len(pw) == 12 and ac.password_problem(pw) is None


def test_username_rule():
    for ok in ("melia", "Budi.S-1", "a_b"):
        assert ac.USERNAME_RE.match(ok)
    for bad in ("ab", "dengan spasi", "x" * 41, "koma,", ""):
        assert not ac.USERNAME_RE.match(bad)


@pytest.mark.parametrize("fields,needle", [
    ({"username": "ab", "name": "X", "role": "supervisor", "auth_mode": "local"}, "Username"),
    ({"username": "budi", "name": " ", "role": "supervisor", "auth_mode": "local"}, "Nama"),
    ({"username": "budi", "name": "Budi", "role": "admin", "auth_mode": "local"}, "Peran"),
    ({"username": "budi", "name": "Budi", "role": "supervisor", "auth_mode": "ldap"}, "Sumber"),
])
def test_create_user_refuses_bad_input(fields, needle):
    with pytest.raises(HTTPException) as e:
        asyncio.run(ac.create_user(by="uji", **fields))
    assert e.value.status_code == 422 and needle in e.value.detail


def test_rosy_password_is_refused_when_the_company_has_no_rosy(monkeypatch):
    monkeypatch.setenv("ROSY_FEED_ENABLED", "false")
    with pytest.raises(HTTPException) as e:
        asyncio.run(ac.create_user("budi", "Budi", "supervisor", "rosy", "uji"))
    assert "tidak terhubung ke ROSY" in e.value.detail


def test_a_temporary_password_blocks_every_hr_route_until_changed():
    with pytest.raises(HTTPException) as e:
        asyncio.run(core.require_hr({"role": "manager_hrd", "must_change_password": True}))
    assert e.value.status_code == 403 and "Ganti kata sandi" in e.value.detail
    with pytest.raises(HTTPException):
        asyncio.run(core.require_manager({"role": "manager_hrd", "must_change_password": True}))
    assert asyncio.run(core.require_hr({"role": "supervisor"}))["role"] == "supervisor"


def test_master_admin_is_not_a_payroll_role_and_only_it_passes_the_admin_gate():
    assert core.MASTER_ADMIN == "master_admin" and core.MASTER_ADMIN not in core.HR_ROLES   # tanpa akses data gaji
    assert core.MASTER_ADMIN in ac.ROLES
    assert asyncio.run(core.require_master_admin({"role": "master_admin"}))["role"] == "master_admin"
    for role in ("manager_hrd", "supervisor", None):
        with pytest.raises(HTTPException) as e:
            asyncio.run(core.require_master_admin({"role": role}))
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:                       # Master Admin ditolak di semua rute gaji
        asyncio.run(core.require_hr({"role": "master_admin"}))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        asyncio.run(core.require_manager({"role": "master_admin"}))


def test_master_admin_cannot_reset_own_password_it_would_lock_the_session():
    with pytest.raises(HTTPException) as e:
        asyncio.run(ac.reset_password("u-1", me={"id": "u-1"}))
    assert e.value.status_code == 409 and "akun sendiri" in e.value.detail
