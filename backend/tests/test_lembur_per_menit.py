"""Lembur dibayar PER MENIT dengan tarif per karyawan (keputusan user 11 Okt 2026), sama dengan rekap Excel lembur
driver yang sudah berjalan: total menit × tarif/60. ROSY mengirim menit disetujui per klaim (tanpa pembulatan 30 menit),
RUSA yang menghitung rupiahnya."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402

from engine import compute_payslip  # noqa: E402
from pdf_service import _jam_menit, payslip_lines  # noqa: E402
from test_rasa_aturan import CFG, EMP, _day  # noqa: E402

# Excel "09. LEMBURAN DRIVER 2026 SEPTEMBER ANA": durasi tiap perjalanan (16:00 s/d FINISH) dalam menit
EXCEL_ANA = [228, 148, 314, 82, 125, 80, 100, 189, 228, 64]


def _slip(rate, minutes):
    emp = {**EMP, "overtime_hourly_rate": rate}
    slip = compute_payslip(emp, [_day("hadir")], CFG, {"overtime_hours": sum(minutes) / 60})
    slip["employee"] = {"nik": "2019031", "name": "Contoh Driver", "department": "Logistic",
                        "bank_name": "Bank Syariah Indonesia", "bank_code": "bsi", "bank_account_number": "7123456789",
                        "birth_date": "1990-01-01"}
    return slip


def test_sama_dengan_excel_driver():
    # Excel: 25 jam 58 menit → (25 × 10.000) + (58/60 × 10.000) = 259.666,67
    slip = _slip(10000, EXCEL_ANA)
    assert sum(EXCEL_ANA) == 25 * 60 + 58
    assert slip["overtime_pay"] == 259667
    assert slip["overtime_pay"] != 235000                     # bukan pembulatan lama per 30 menit (23 j 30 m)


@pytest.mark.parametrize("rate, expected", [(10000, 259667), (12500, 324583), (25000, 649167)])
def test_tarif_mengikuti_isian_per_karyawan(rate, expected):
    assert _slip(rate, EXCEL_ANA)["overtime_pay"] == expected


def test_tanpa_tarif_tidak_dibayar():
    assert _slip(0, EXCEL_ANA)["overtime_pay"] == 0


@pytest.mark.parametrize("hours, text", [(1558 / 60, "25 jam 58 menit"), (2.5, "2 jam 30 menit"), (3, "3 jam"),
                                         (64 / 60, "1 jam 4 menit"), (45 / 60, "45 menit")])
def test_label_jam_menit(hours, text):
    assert _jam_menit(hours) == text


def test_slip_mencetak_jam_dan_menit():
    earn, _ = payslip_lines(_slip(10000, EXCEL_ANA))
    assert any(r[0] == "Lembur (25 jam 58 menit)" and r[1] == 259667 for r in earn)
