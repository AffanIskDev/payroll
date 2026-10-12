"""Slip labels that depend on who the employee is — one rule for the review page, the PDF and the dashboard."""

# Divisi Pelayanan: tunjangan jabatannya disebut "Bonus Threshold" di review payroll & slip gaji (permintaan HRD
# 10 Okt 2026, diterapkan 12 Okt). Uangnya sama, hanya namanya — perhitungan & pajaknya tetap tunjangan jabatan.
BONUS_THRESHOLD_DEPARTMENTS = {"pelayanan"}


def position_allowance_label(emp: dict) -> str:
    dept = " ".join(str((emp or {}).get("department") or "").split()).lower()
    return "Bonus Threshold" if dept in BONUS_THRESHOLD_DEPARTMENTS else "Tunjangan Jabatan"
