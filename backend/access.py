"""Who may use RASA, decided from the ROSY position (jabatan) HAM returns at login.

User decision 9 Oct 2026: no user management in RASA — access follows the employee's position in ROSY.
- manager_hrd: level General Manager (oversees HRD), or a Manager-level HRD position in Human Capital
- supervisor:  a Koordinator-level (SPV) HRD position in Human Capital
Other Human Capital positions (Supervisor Klinik, Supervisor Diklat, staff) get no access: payroll shows
everyone's salary."""
import os

ROLE_LABELS = {"manager_hrd": "Manager HRD", "supervisor": "Supervisor"}
_RANK = {None: 0, "supervisor": 1, "manager_hrd": 2}


def _norm(v) -> str:
    return " ".join(str(v or "").split()).lower()


def role_for(jabatan: list) -> str | None:
    """Highest role over the employee's positions; None = no access."""
    dept_ham = _norm(os.environ.get("RASA_DEPT_HAM", "DEP-0001"))
    best = None
    for j in jabatan or []:
        level, name = _norm(j.get("level")), _norm(j.get("nama"))
        hrd = _norm(j.get("department_id")) == dept_ham and "hrd" in name.split()
        role = None
        if level == "general manager" or (hrd and level == "manager"):
            role = "manager_hrd"
        elif hrd and level == "koordinator":
            role = "supervisor"
        if _RANK[role] > _RANK[best]:
            best = role
    return best
