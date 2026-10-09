"""Payroll calculation engine (PP 35/2021, PP 58/2023, PMK 168/2023, UU Naker)."""
import math
import re

TER_A = [(5400000, 0), (5650000, 0.25), (5950000, 0.5), (6300000, 0.75), (6750000, 1), (7500000, 1.25),
         (8550000, 1.5), (9650000, 1.75), (10050000, 2), (10350000, 2.25), (10700000, 2.5), (11050000, 3),
         (11600000, 3.5), (12500000, 4), (13750000, 5), (15100000, 6), (16950000, 7), (19750000, 8),
         (24150000, 9), (26450000, 10), (28000000, 11), (30050000, 12), (32400000, 13), (35400000, 14),
         (39100000, 15), (43850000, 16), (47800000, 17), (51400000, 18), (56300000, 19), (62200000, 20),
         (68600000, 21), (77500000, 22), (89000000, 23), (103000000, 24), (125000000, 25), (157000000, 26),
         (206000000, 27), (337000000, 28), (454000000, 29), (550000000, 30), (695000000, 31),
         (910000000, 32), (1400000000, 33)]
TER_B = [(6200000, 0), (6500000, 0.25), (6850000, 0.5), (7300000, 0.75), (9200000, 1), (10750000, 1.5),
         (11250000, 2), (11600000, 2.5), (12600000, 3), (13600000, 4), (14950000, 5), (16400000, 6),
         (18450000, 7), (21850000, 8), (26000000, 9), (27700000, 10), (29350000, 11), (31450000, 12),
         (33950000, 13), (37100000, 14), (41100000, 15), (45800000, 16), (49500000, 17), (53800000, 18),
         (58500000, 19), (64000000, 20), (71000000, 21), (80000000, 22), (93000000, 23), (109000000, 24),
         (129000000, 25), (163000000, 26), (211000000, 27), (374000000, 28), (459000000, 29),
         (555000000, 30), (704000000, 31), (957000000, 32), (1405000000, 33)]
TER_C = [(6600000, 0), (6950000, 0.25), (7350000, 0.5), (7800000, 0.75), (8850000, 1), (9800000, 1.25),
         (10950000, 1.5), (11200000, 1.75), (12050000, 2), (12950000, 3), (14150000, 4), (15550000, 5),
         (17050000, 6), (19500000, 7), (22700000, 8), (26600000, 9), (28100000, 10), (30100000, 11),
         (32600000, 12), (35400000, 13), (38900000, 14), (43000000, 15), (47400000, 16), (51200000, 17),
         (55800000, 18), (60400000, 19), (66700000, 20), (74500000, 21), (83200000, 22), (95600000, 23),
         (110000000, 24), (134000000, 25), (169000000, 26), (221000000, 27), (390000000, 28),
         (463000000, 29), (561000000, 30), (709000000, 31), (965000000, 32), (1419000000, 33)]
TER_TABLES = {"A": TER_A, "B": TER_B, "C": TER_C}

# PPT "Review Ketentuan dan Perhitungan Payroll Karyawan" (slide 4): which pay parts an absence day costs.
# Cut only the attendance allowance (gapok & jabatan paid): cuti tahunan (incl. cuti bersama), sakit,
# cuti khusus, cuti melahirkan, ibadah. Cut gapok + jabatan + attendance: alfa/mangkir, izin, unpaid leave.
# Never cut: present, dinas, dispensasi, libur.
ATT_CUT_LEAVES = ("sick_with_certificate", "annual_leave", "statutory_leave", "maternity_leave", "religious_leave")
FULL_CUT_LEAVES = ("alpha", "permission_leave", "approved_unpaid_leave")
BPJS_TK_PROGRAMS = ("jkk", "jkm", "jht", "jp")


def resolve_ptkp(emp: dict) -> str:
    # HAM sends the effective status (married women already TK/0); only derive it when absent
    status = str(emp.get("ptkp_status") or "").replace(" ", "").upper()
    if re.fullmatch(r"(TK|K)/[0-3]", status):
        return status
    dep = min(int(emp.get("dependents_count") or 0), 3)
    if emp.get("marital_status") == "K":
        if emp.get("gender") == "P" and not emp.get("has_husband_certificate"):
            return "TK/0"
        return f"K/{dep}"
    return f"TK/{dep}"


def ter_category(ptkp: str) -> str:
    if ptkp in ("TK/0", "TK/1", "K/0"):
        return "A"
    if ptkp == "K/3":
        return "C"
    return "B"


def ter_rate(category: str, gross: float) -> float:
    for upper, rate in TER_TABLES[category]:
        if gross <= upper:
            return rate
    return 34


def calc_discipline(logs: list) -> dict:
    """Poin Presensi (waterfall non-duplikasi Rule 1-4) + Poin Absensi (hari tidak hadir pemotong, PPT)."""
    r1 = r2 = small_minutes = att_days = basic_days = 0
    mid, by_type = [], {}
    for log in sorted(logs, key=lambda x: x["work_date"]):
        lt = log.get("leave_type", "present")
        if lt in ATT_CUT_LEAVES or lt in FULL_CUT_LEAVES:
            att_days += 1
            by_type[lt] = by_type.get(lt, 0) + 1
            if lt in FULL_CUT_LEAVES:
                basic_days += 1
            continue
        if lt != "present":
            continue
        events = []
        if log.get("is_missing_check_in"):
            r1 += 1
        elif (log.get("minutes_late") or 0) > 0:
            events.append(int(log["minutes_late"]))
        if log.get("is_missing_check_out"):
            r1 += 1
        elif (log.get("minutes_early_leave") or 0) > 0:
            events.append(int(log["minutes_early_leave"]))
        for m in events:
            if m >= 60:
                r2 += 1
            elif m >= 15:
                mid.append(m)
            else:
                small_minutes += m
    r3 = len(mid) // 3
    rem = len(mid) % 3
    carried = mid[len(mid) - rem:] if rem else []
    r4_minutes = small_minutes + sum(carried)
    r4 = r4_minutes // 60
    return {
        "rule1_points": r1, "rule2_points": r2, "rule3_points": r3, "rule3_events": len(mid),
        "rule3_carried_minutes": carried, "rule4_minutes": r4_minutes, "rule4_points": r4,
        "rule4_forfeited_minutes": r4_minutes % 60, "small_minutes": small_minutes,
        "total_points": r1 + r2 + r3 + r4, "attendance_cut_days": att_days, "basic_cut_days": basic_days,
        "absence_points": att_days, "absence_by_type": by_type,
    }


def wage_multiplier(status: str, month: int) -> float:
    month = max(int(month or 1), 1)
    if status == "unpaid_leave":
        return 0.0
    if status == "prolonged_illness":
        return 1.0 if month <= 4 else 0.75 if month <= 8 else 0.5 if month <= 12 else 0.25
    if status == "work_accident_stmb":
        return 1.0 if month <= 12 else 0.5
    return 1.0


def calc_bpjs(emp: dict, cfg: dict) -> dict:
    basic = float(emp.get("basic_salary") or 0)
    umk = float(cfg.get("UMK_BEKASI_REGENCY", 0))
    kes_cap = float(cfg.get("BPJS_KES_MAX_WAGE", 12000000))
    jp_cap = float(cfg.get("BPJS_JP_MAX_WAGE", 0))
    r = dict.fromkeys(["kes_base", "kes_company", "kes_employee", "jkk", "jkm", "jht_company",
                       "jht_employee", "jp_base", "jp_company", "jp_employee"], 0)
    # per-program membership from HAM's salary template; falls back to the two legacy flags
    programs = emp.get("bpjs_programs") or {}
    joined = {"kes": programs.get("kes", emp.get("has_bpjs_kes", True)),
              **{p: programs.get(p, emp.get("has_bpjs_tk", True)) for p in BPJS_TK_PROGRAMS}}
    if joined["kes"]:
        r["kes_base"] = round(min(max(basic, umk), kes_cap))
        r["kes_company"] = round(r["kes_base"] * 0.04)
        r["kes_employee"] = round(r["kes_base"] * 0.01)
    if joined["jkk"]:
        r["jkk"] = round(basic * float(emp.get("jkk_rate") or 0.0024))
    if joined["jkm"]:
        r["jkm"] = round(basic * 0.003)
    if joined["jht"]:
        r["jht_company"] = round(basic * 0.037)
        r["jht_employee"] = round(basic * 0.02)
    if joined["jp"]:
        r["jp_base"] = round(min(basic, jp_cap))
        r["jp_company"] = round(r["jp_base"] * 0.02)
        r["jp_employee"] = round(r["jp_base"] * 0.01)
    return r


PASAL17_BRACKETS = [(60000000, 5), (250000000, 15), (500000000, 25), (5000000000, 30), (float("inf"), 35)]


def ptkp_amount(ptkp: str) -> int:
    status, dep = ptkp.split("/")
    return 54000000 + (4500000 if status == "K" else 0) + 4500000 * int(dep)


def pasal17_tax(pkp: float) -> int:
    tax, lower = 0.0, 0
    for upper, rate in PASAL17_BRACKETS:
        if pkp <= lower:
            break
        tax += (min(pkp, upper) - lower) * rate / 100
        lower = upper
    return math.floor(tax)


def annual_tax_summary(gross_year: float, jht_jp_year: float, months: int, ptkp: str) -> dict:
    biaya_jabatan = min(round(gross_year * 0.05), 500000 * max(1, min(int(months), 12)))
    neto = gross_year - biaya_jabatan - jht_jp_year
    ptkp_val = ptkp_amount(ptkp)
    pkp = math.floor(max(0, neto - ptkp_val) / 1000) * 1000
    return {"biaya_jabatan": biaya_jabatan, "neto_year": neto, "ptkp_amount": ptkp_val, "pkp": pkp,
            "annual_tax": pasal17_tax(pkp)}


def december_reconciliation(ctx: dict, dec_taxable: float, dec_jht_jp: float, ptkp: str) -> dict:
    """Rekonsiliasi PPh 21 masa Desember (Pasal 17 UU HPP)."""
    gross_year = ctx["initial_gross"] + ctx["system_gross"] + dec_taxable
    jht_jp_year = ctx["initial_jht_jp"] + ctx["system_jht_jp"] + dec_jht_jp
    months = ctx.get("initial_months", 0) + ctx["system_months"] + 1
    t = annual_tax_summary(gross_year, jht_jp_year, months, ptkp)
    biaya_jabatan, neto, ptkp_val, pkp, annual_tax = (t["biaya_jabatan"], t["neto_year"], t["ptkp_amount"],
                                                      t["pkp"], t["annual_tax"])
    paid = ctx["initial_pph21"] + ctx["system_pph21"]
    return {
        "tax_year": ctx["tax_year"], "initial_gross": ctx["initial_gross"], "system_gross": ctx["system_gross"],
        "system_months": ctx["system_months"], "december_gross": dec_taxable, "gross_year": gross_year,
        "biaya_jabatan": biaya_jabatan, "jht_jp_year": jht_jp_year, "neto_year": neto, "ptkp_amount": ptkp_val,
        "pkp": pkp, "annual_tax": annual_tax, "pph21_paid_jan_nov": paid, "pph21_december": annual_tax - paid,
        "has_initial_balance": ctx["has_initial_balance"],
    }


def compute_payslip(emp: dict, logs: list, cfg: dict, adj: dict, dec_ctx: dict = None) -> dict:
    wd = int(cfg.get("DEFAULT_WORK_DAYS", 25))
    status = emp.get("payroll_status", "active")
    mult = wage_multiplier(status, emp.get("prolonged_illness_month_count"))
    # directors exempt from attendance assessment in HAM (PresensiHelpers) are never penalised
    disc = calc_discipline([] if emp.get("attendance_exempt") else logs)
    basic = float(emp.get("basic_salary") or 0)
    att = float(emp.get("monthly_attendance_allowance") or 0)
    unpaid = status == "unpaid_leave"

    hours = 0 if unpaid else float(adj.get("overtime_hours") or 0)
    kpi = 0 if unpaid else round(float(adj.get("kpi_incentive") or 0))
    bonus = 0 if unpaid else round(float(adj.get("additional_bonus") or 0))
    kasbon = round(float(adj.get("other_deductions") or 0))
    transport = 0 if unpaid else round(float(adj.get("transport_homecare") or 0))
    overtime_pay = round(hours * float(emp.get("overtime_hourly_rate") or 0))

    basic_paid = round(basic * mult)
    # PPT: during prolonged illness only gapok is paid (100/75/50/25%); jabatan and attendance are not
    position_paid = 0 if status == "prolonged_illness" else round(float(emp.get("position_allowance") or 0) * mult)
    if status == "active":
        # Poin Presensi + Poin Absensi each cost 1/wd of the attendance allowance
        penalty_days = min(disc["total_points"] + disc["absence_points"], wd)
        penalty_amount = round(penalty_days / wd * att)
        # split for the slip (Potongan Absensi / Potongan Presensi); absence days first, presensi takes the rest,
        # so the two always add up to penalty_amount even when the month is capped
        absence_penalty = min(round(min(disc["absence_points"], wd) / wd * att), penalty_amount)
        presence_penalty = penalty_amount - absence_penalty
        # alfa/izin days cost gapok and jabatan too, capped at 100% (a month of alfa must not yield negative pay)
        cut_days = min(disc["basic_cut_days"], wd)
        absent_deduction = round(cut_days / wd * basic)
        position_deduction = round(cut_days / wd * position_paid)
    else:
        penalty_days = wd
        penalty_amount = round(att)
        absent_deduction = position_deduction = absence_penalty = presence_penalty = 0
    attendance_net = round(att - penalty_amount)

    bp = calc_bpjs(emp, cfg) if not unpaid else calc_bpjs({}, {})
    bpjs_advance = 0
    if unpaid:
        adv = calc_bpjs(emp, cfg)
        bpjs_advance = sum(adv[k] for k in ("kes_company", "kes_employee", "jkk", "jkm", "jht_company",
                                            "jht_employee", "jp_company", "jp_employee"))
    tunj_kes = bp["kes_company"]
    tunj_tk = bp["jkk"] + bp["jkm"] + bp["jht_company"] + bp["jp_company"]

    base_earn = (basic_paid - absent_deduction + position_paid - position_deduction + attendance_net + overtime_pay
                 + transport + kpi + bonus)
    gross = base_earn + tunj_kes + tunj_tk
    taxable = base_earn + bp["kes_company"] + bp["jkk"] + bp["jkm"]

    ptkp = resolve_ptkp(emp)
    cat = ter_category(ptkp)
    rate = ter_rate(cat, taxable)
    pph21 = math.floor(taxable * rate / 100)
    recon = None
    if dec_ctx is not None:
        recon = december_reconciliation(dec_ctx, taxable, bp["jht_employee"] + bp["jp_employee"], ptkp)
        pph21 = recon["pph21_december"]

    iuran_kes = bp["kes_company"] + bp["kes_employee"]
    iuran_tk = bp["jkk"] + bp["jkm"] + bp["jht_company"] + bp["jht_employee"] + bp["jp_company"] + bp["jp_employee"]
    total_ded = iuran_kes + iuran_tk + pph21 + kasbon
    thp = gross - total_ded

    return {
        "payroll_status": status, "wage_multiplier": mult,
        "basic_salary": basic_paid, "basic_salary_contract": round(basic),
        "position_allowance": position_paid, "position_deduction_amount": position_deduction,
        "attendance_allowance_base": round(att), "attendance_allowance": attendance_net,
        "overtime_hours": hours, "overtime_pay": overtime_pay, "transport_homecare": transport,
        "kpi_incentive": kpi, "additional_bonus": bonus,
        "tunjangan_bpjs_kes": tunj_kes, "tunjangan_bpjs_tk": tunj_tk,
        "gross_earnings": gross, "taxable_gross": taxable,
        "late_penalty_points": disc["total_points"], "late_penalty_days": penalty_days,
        "late_penalty_amount": penalty_amount, "absence_points": disc["absence_points"], "work_days": wd,
        "presence_penalty_amount": presence_penalty, "absence_penalty_amount": absence_penalty,
        "absent_days": disc["basic_cut_days"], "absent_deduction_amount": absent_deduction,
        "iuran_bpjs_kes_total": iuran_kes, "iuran_bpjs_tk_total": iuran_tk,
        "pph21_amount": pph21, "pph21_method": "pasal17" if recon else "ter", "tax_reconciliation": recon,
        "ptkp_status": ptkp, "ter_category": cat, "ter_rate": rate,
        "other_deductions": kasbon, "total_deductions": total_ded, "take_home_pay": thp,
        "bpjs_company_advance": bpjs_advance,
        "discipline": disc, "bpjs": bp, "terbilang": terbilang(thp),
    }


_SATUAN = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]


def _words(n: int) -> str:
    if n < 12:
        return _SATUAN[n]
    if n < 20:
        return f"{_SATUAN[n - 10]} Belas"
    if n < 100:
        return f"{_SATUAN[n // 10]} Puluh {_words(n % 10)}".strip()
    if n < 200:
        return f"Seratus {_words(n - 100)}".strip()
    if n < 1000:
        return f"{_SATUAN[n // 100]} Ratus {_words(n % 100)}".strip()
    if n < 2000:
        return f"Seribu {_words(n - 1000)}".strip()
    for div, name in ((10 ** 12, "Triliun"), (10 ** 9, "Miliar"), (10 ** 6, "Juta"), (1000, "Ribu")):
        if n >= div:
            return f"{_words(n // div)} {name} {_words(n % div)}".strip()
    return ""


def terbilang(amount: float) -> str:
    n = int(round(amount))
    if n == 0:
        return "Nol Rupiah"
    prefix = "Minus " if n < 0 else ""
    return f"{prefix}{_words(abs(n))} Rupiah"
