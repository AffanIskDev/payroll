"""Slip labels that depend on who the employee is — one rule for the review page, the PDF and the dashboard."""

# PJUnit = jabatan "Penanggung Jawab unit" di ROSY (13 Okt 2026). Hanya PJUnit yang tunjangan jabatannya disebut
# "Bonus Threshold" di review payroll & slip gaji (permintaan HRD 10 Okt 2026, diterapkan 12 Okt; sejak 14 Okt 2026
# menurut JABATAN PJ Unit saja, bukan divisi/department — Manajer, Supervisor, atau Perawat Pelayanan tetap "Tunjangan
# Jabatan"). Uangnya sama, hanya namanya — perhitungan & pajaknya tetap tunjangan jabatan. Potongan Tidak Mencapai
# Target PJUnit diambil dari Bonus Threshold-nya sendiri — aturan hitungnya di engine.compute_payslip
PJUNIT_POSITIONS = {"penanggung jawab unit", "pj unit", "pjunit"}

# Keterangan di bawah baris Bonus Threshold PJUnit yang terpotong karena tidak mencapai target (user 14 Okt 2026; dulu
# "Rp x, dipotong Rp y karena tidak mencapai target"). Review payroll (Workbench.jsx) memakai kalimat yang sama.
PJUNIT_TARGET_NOTE = "Income Unit Minimal 20 jt"


def _norm(v) -> str:
    return " ".join(str(v or "").split()).lower()


def position_allowance_label(emp: dict) -> str:
    return "Bonus Threshold" if is_pjunit(emp) else "Tunjangan Jabatan"


def is_pjunit(emp: dict) -> bool:
    return _norm((emp or {}).get("position")) in PJUNIT_POSITIONS
