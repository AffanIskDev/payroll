"""Multi-PT (6 Nov 2026): data gaji hanya bisa disentuh dengan PT aktif. Tes lama ditulis untuk satu PT, jadi setiap tes
berjalan sebagai CP-001 kecuali tesnya memasang PT lain sendiri (core.dengan_pt)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")
os.environ.setdefault("JWT_SECRET", "uji")

import core  # noqa: E402


@pytest.fixture(autouse=True)
def pt_aktif_bawaan():
    with core.dengan_pt("CP-001"):
        yield
