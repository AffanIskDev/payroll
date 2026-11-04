"""Presensi dari RUMATKU (4 Nov 2026): siapa yang ditarik, cara mencocokkan, dan jendela masuk/keluar. Murni logika (tanpa jaringan/DB)."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

import integrations  # noqa: E402


def _emp(i, uid="", exempt=False, **kw):
    return {"id": f"e{i}", "nik": f"N{i}", "name": f"Karyawan {i}", "user_id_rumatku": uid, "attendance_exempt": exempt, **kw}


def _fakta(uid, tgl, status="hadir"):
    return {"user_id_rumatku": uid, "nik": None, "work_date": tgl, "status_ham": status, "hari_kerja": True,
            "check_in_time": "08:00", "check_out_time": "16:00", "minutes_late": 0, "minutes_early_leave": 0,
            "is_missing_check_in": False, "is_missing_check_out": False, "ham_points": 0}


def test_hanya_karyawan_bertaut_dan_tak_bebas_presensi_yang_ditarik(monkeypatch):
    dipanggil = []

    async def palsu(params):
        dipanggil.append(params)
        return {"data": [_fakta(u, "2026-09-01") for u in params["user_ids"].split(",")], "meta": {"effective_end": "2026-09-30"}}

    monkeypatch.setattr(integrations, "_get_rumatku", palsu)
    emps = [_emp(1, "USR-00001"), _emp(2, "USR-00002", exempt=True), _emp(3, ""), _emp(4, "USR-00004")]
    rows, meta = asyncio.run(integrations.fetch_attendance_rumatku("2026-09-01", "2026-09-30", emps))
    assert len(dipanggil) == 1
    assert dipanggil[0]["user_ids"] == "USR-00001,USR-00004"          # yang bebas presensi & belum bertaut TIDAK ikut
    assert {r["user_id_rumatku"] for r in rows} == {"USR-00001", "USR-00004"}
    assert [u["rusa_id"] for u in meta["unlinked"]] == ["e3"]          # dilaporkan, bukan dibuang diam-diam
    assert meta["effective_end"] == "2026-09-30" and meta["source"] == "rumatku"


def test_dipecah_per_batch(monkeypatch):
    monkeypatch.setattr(integrations, "FEED_BATCH", 2)
    panggilan = []

    async def palsu(params):
        panggilan.append(params["user_ids"].split(","))
        return {"data": [], "meta": {}}

    monkeypatch.setattr(integrations, "_get_rumatku", palsu)
    emps = [_emp(i, f"USR-0000{i}") for i in range(1, 6)]
    asyncio.run(integrations.fetch_attendance_rumatku("2026-09-01", "2026-09-30", emps))
    assert [len(b) for b in panggilan] == [2, 2, 1]


def test_tanpa_karyawan_bertaut_tidak_memanggil_feed(monkeypatch):
    async def tak_boleh(params):
        raise AssertionError("feed tidak boleh dipanggil")

    monkeypatch.setattr(integrations, "_get_rumatku", tak_boleh)
    rows, meta = asyncio.run(integrations.fetch_attendance_rumatku("2026-09-01", "2026-09-30", [_emp(1, "")]))
    assert rows == [] and len(meta["unlinked"]) == 1


def test_galat_feed_diteruskan(monkeypatch):
    async def galat(params):
        raise RuntimeError("RUMATKU 409: Kalender Hari Kerja belum lengkap")

    monkeypatch.setattr(integrations, "_get_rumatku", galat)
    with pytest.raises(RuntimeError, match="Kalender"):
        asyncio.run(integrations.fetch_attendance_rumatku("2026-09-01", "2026-09-30", [_emp(1, "USR-00001")]))


def test_jendela_masuk_keluar():
    e = {"join_date": "2026-09-10", "exit_date": "2026-09-20"}
    assert not integrations.in_work_window(e, "2026-09-09")
    assert integrations.in_work_window(e, "2026-09-10")
    assert integrations.in_work_window(e, "2026-09-20")
    assert not integrations.in_work_window(e, "2026-09-21")
    assert integrations.in_work_window({}, "2026-09-05")              # tanpa tanggal = tak dibatasi


def test_sumber_presensi_dari_env(monkeypatch):
    monkeypatch.delenv("ATTENDANCE_SOURCE", raising=False)
    assert not integrations.attendance_from_rumatku()
    monkeypatch.setenv("ATTENDANCE_SOURCE", "RUMATKU")
    assert integrations.attendance_from_rumatku() and integrations.mode("RUMATKU") == "rumatku"
    assert integrations.mode("ROSY") != "rumatku"


def test_akun_milik_pt_lain_ditandai_bukan_dihitung(monkeypatch):
    async def palsu(params):
        return {"data": [_fakta("USR-00001", "2026-09-01")], "meta": {"user_ids_tidak_ditemukan": ["USR-00002"]}}

    monkeypatch.setattr(integrations, "_get_rumatku", palsu)
    emps = [_emp(1, "USR-00001"), _emp(2, "USR-00002")]
    rows, meta = asyncio.run(integrations.fetch_attendance_rumatku("2026-09-01", "2026-09-30", emps))
    assert [r["user_id_rumatku"] for r in rows] == ["USR-00001"]
    assert [(u["rusa_id"], u["alasan"]) for u in meta["unlinked"]] == [("e2", "Akun RUMATKU bukan milik perusahaan ini")]
    assert meta["employees"] == 1
