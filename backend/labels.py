"""Slip labels that depend on who the employee is — one rule for the review page, the PDF and the dashboard."""

# Divisi Pelayanan: tunjangan jabatannya disebut "Bonus Threshold" di review payroll & slip gaji (permintaan HRD
# 10 Okt 2026, diterapkan 12 Okt). Uangnya sama, hanya namanya — perhitungan & pajaknya tetap tunjangan jabatan.
BONUS_THRESHOLD_DEPARTMENTS = {"pelayanan"}

# PJUnit = jabatan "Penanggung Jawab unit" di ROSY (13 Okt 2026). Potongan Tidak Mencapai Target-nya diambil dari
# Bonus Threshold-nya sendiri — aturan hitungnya di engine.compute_payslip
PJUNIT_POSITIONS = {"penanggung jawab unit", "pj unit", "pjunit"}


def _norm(v) -> str:
    return " ".join(str(v or "").split()).lower()


def position_allowance_label(emp: dict) -> str:
    dept = _norm((emp or {}).get("department"))
    return "Bonus Threshold" if dept in BONUS_THRESHOLD_DEPARTMENTS else "Tunjangan Jabatan"


def is_pjunit(emp: dict) -> bool:
    emp = emp or {}
    return (_norm(emp.get("department")) in BONUS_THRESHOLD_DEPARTMENTS
            and _norm(emp.get("position")) in PJUNIT_POSITIONS)
