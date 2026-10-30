"""Batch Payment BSI: the pipe-separated TXT HRD uploads to BSI's bulk payroll transfer — the same file ROSY HAM makes
(PayrollModules::exportBatchPayment, live since 30 Sep 2026), ported rule for rule (user request 10 Oct 2026).

BSI receives the TXT, not its Template_Batch_Payment_v1.8.1.xlsb: that workbook is only a helper whose user guide says
to copy the "Results" sheet into Notepad. Layout, as in the official sample embedded in the workbook:

    0|<UPLOAD FILE ID>|<yyyy-mm-dd>|<row count>|<total amount>|
    0|BENEFICIARY ACCT (35)|BENEFICIARY ACCT NAME |...|
    1|<account>|<name>|IDR|<amount>|<cust ref>|<message>|||

Every line ends with '|', lines are CRLF and the last one has no line break ("make sure there are no empty lines in the
last line"). The file moves money, so it is all or nothing: one bad row and no file is made — a half file pays some
people and nobody notices the rest until they complain."""
import math
import re

from periods import BULAN

# mt_bank.kode of BK-0001 (ROSY checks the id, HAM's feed sends the code). Batch type "Payroll" has no bank column:
# an account at another bank would be read as a BSI account — money to a stranger
BANK_CODE = "BSI"
ACCOUNT_LEN = 10   # BSI account length; rejects placeholders such as '1' or '00000'
MAX_ROWS = 50000   # per file, template user guide v1.8.1
NAME_LEN = 35      # ROSY's assumption, kept: the official header gives no length for the name column
# Verbatim copy of row 9 of the template's "Payroll" sheet, as ROSY writes it — including the trailing space in
# "BENEFICIARY ACCT NAME ". The "Results" sheet copies the header as is, so retyping it "neatly" would make our file
# differ from the template's.
HEADER = ("BENEFICIARY ACCT (35)", "BENEFICIARY ACCT NAME ", "CREDIT AMOUNT CCY", "AMOUNT", "CUST REF NO",
          "MESSAGE (65)", "EXTENDED PAYMENT DETAIL", "BENEFICIARY NOTIF EMAIL(100)", "SMS NOTIF (100)")

# '|' separates columns and a line break separates records: either one inside a name shifts every later column — a
# payment to the wrong account. NBSP, zero-width characters and BOM look like a space (or nothing) but change the
# bytes the bank reads; ROSY found U+00A0 in a real name.
_SEPARATORS = re.compile(r"[|\s ​‌‍﻿]+")


def clean(value, max_len: int) -> str:
    return _SEPARATORS.sub(" ", "" if value is None else str(value)).strip()[:max_len]


def _rp(v: float) -> str:
    return f"Rp {round(v):,}".replace(",", ".")


def _month(month: str) -> tuple:
    """'2026-09' -> (2026, 9)."""
    return int(month[:4]), int(month[5:7])


def account_name(emp: dict) -> str:
    """HAM's "Nama di Rekening" (nama_rekening). Required since 14 Oct 2026 (user): account_problems() holds back an
    employee without it, so the employee's name is no longer written in its place (ROSY's batchNamaPenerima still
    does). Titles are not stripped here: an automatic cleaner got real names wrong, so HRD fixes the name in ROSY
    where it can be seen."""
    return str(emp.get("bank_account_name") or "").strip()


def unpaid_zero(slip: dict) -> bool:
    """Cuti tanpa upah (ROSY "Unpaid", is_paid 0): RUSA still makes a Rp 0 slip where ROSY makes none, so it stays out
    of the file — the file ROSY would make — instead of blocking it as a Rp 0 transfer."""
    return slip.get("payroll_status") == "unpaid_leave" and float(slip.get("take_home_pay") or 0) <= 0


def account_problems(emp: dict) -> list:
    """What keeps an employee's pay from going out through Batch Payment BSI, as (kind, note) pairs; empty = ready.
    ROSY's batchMasalahBaris rules for the account, plus "Nama di Rekening" (user 14 Oct 2026: no account number, no
    account name or not BSI = the payroll cannot be processed). The bank file, "Ajukan ke Manager" and Lock & Approve
    all use it."""
    out = []
    if str(emp.get("bank_code") or "").strip().upper() != BANK_CODE:
        bank = emp.get("bank_name") or emp.get("bank_code") or "bank belum diisi"
        out.append(("Bank bukan BSI", f"{bank} — harus dibayar lewat batch terpisah"))
    acct = str(emp.get("bank_account_number") or "").strip()
    if not acct:
        out.append(("Rekening kosong", "nomor rekening belum diisi"))
    elif not re.fullmatch(r"[0-9]+", acct):
        out.append(("Rekening bukan angka", f'berisi "{acct}"'))
    elif len(acct) != ACCOUNT_LEN:
        out.append(("Panjang rekening ganjil", f"{acct} = {len(acct)} digit, seharusnya {ACCOUNT_LEN}"))
    elif not acct.strip("0"):
        out.append(("Rekening nol semua", f'"{acct}"'))
    if not account_name(emp):
        out.append(("Nama rekening kosong", "Nama di Rekening belum diisi di ROSY"))
    return out


def row_problems(slip: dict, emp) -> list:
    """What keeps one slip out of the file, as (kind, note) pairs; empty = ready (ROSY's batchMasalahBaris)."""
    if emp is None:
        return [("Karyawan tidak ditemukan", f"employee_id {slip['employee_id']} tidak ada di data karyawan RUSA")]
    out = account_problems(emp)
    thp = float(slip.get("take_home_pay") or 0)
    if thp <= 0:
        out.append(("Nominal tidak wajar", f"Total Diterima = {_rp(thp)}"))
    return out


def approval_blockers(slips: list, employees: dict) -> list:
    """The employees whose account blocks "Ajukan ke Manager" and Lock & Approve (user 14 Oct 2026), one entry each with
    all its problems: every slip not approved yet, except the Rp 0 unpaid-leave ones, which transfer nothing (the bank
    file leaves them out too). Only the account rules — the amount is the slip's business, not the account's.
    employees: RUSA employee docs by id, bank data as last synced from ROSY (what the bank file reads, not the slip's
    snapshot)."""
    out = []
    for s in slips:
        if s.get("status") == "approved" or unpaid_zero(s):
            continue
        emp = employees.get(s["employee_id"])
        found = account_problems(emp) if emp else [("Karyawan tidak ditemukan", "tidak ada di data karyawan RUSA")]
        if found:
            emp, snap = emp or {}, s.get("employee") or {}
            out.append({"employee_id": s["employee_id"], "nik": snap.get("nik") or emp.get("nik"),
                        "name": snap.get("name") or emp.get("name") or s["employee_id"],
                        "bank": emp.get("bank_name") or emp.get("bank_code") or "",
                        "account_number": str(emp.get("bank_account_number") or "").strip(),
                        "account_name": account_name(emp),
                        "problems": [{"kind": k, "note": n} for k, n in found]})
    return sorted(out, key=lambda b: str(b["name"]).casefold())


def build(slips: list, employees: dict, month: str, upload_date: str, label: str = "GAJI") -> dict:
    """slips: the payslips of one period, any status (as in ROSY); employees: RUSA employee docs by id (bank data as
    last synced from ROSY); month: 'YYYY-MM'. Returns {"problems": [...]} when any row blocks the file, else the file text and its
    summary. Raises ValueError when the rows exceed what one file may hold."""
    year, mon = _month(month)
    message = clean(f"{label} {BULAN[mon - 1].upper()} {year}", 65)
    problems, rows, skipped, total = [], [], [], 0
    for s in sorted(slips, key=lambda s: (s["employee"].get("name") or "").casefold()):
        if unpaid_zero(s):
            skipped.append(str(s["employee"].get("nik") or ""))
            continue
        emp = employees.get(s["employee_id"])
        found = row_problems(s, emp)
        if found:
            # every slip is still checked, so HRD gets the whole list in one go
            problems += [{"nik": s["employee"].get("nik"), "name": s["employee"].get("name"), "kind": k, "note": n}
                         for k, n in found]
            continue
        amount = math.floor(float(s["take_home_pay"]))  # the bank refuses fractions; never pay more than the slip
        total += amount
        # CUST REF NO emptied in ROSY 8 Sep 2026 (the bank file carries no NIK) — emptied, not removed: the file is
        # positional and every row must stay aligned with HEADER. Extended detail, email and SMS stay empty as in the
        # official sample: filled in, the BANK notifies every employee (SMS is usually billed per message).
        rows.append(["1", str(emp["bank_account_number"]).strip(), clean(account_name(emp), NAME_LEN), "IDR",
                     str(amount), "", message, "", "", ""])
    if problems:
        return {"problems": problems}
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Jumlah baris {len(rows)} melebihi batas {MAX_ROWS} per berkas")
    # UPLOAD FILE ID: max 10 characters, unique per upload date; derived from the month so HRD can predict it
    lines = [f"0|{label.replace(' ', '')[:6]}{year % 100:02d}{mon:02d}|{upload_date}|{len(rows)}|{total}|", "0|" + "|".join(HEADER) + "|"]
    lines += ["|".join(r) + "|" for r in rows]
    return {"problems": [], "text": "\r\n".join(lines), "count": len(rows), "total": total, "skipped": skipped}


def file_name(company, month: str, label: str = "") -> str:
    """'BatchPayment-RUMAT-September-2026.txt', ROSY's name for the same file."""
    year, mon = _month(month)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (company or {}).get("nama") or "").strip("-")
    kind = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-")  # "THR", "Bonus-Tahunan"; kosong = gaji, nama seperti dulu
    return f"BatchPayment-{slug + '-' if slug else ''}{kind + '-' if kind else ''}{BULAN[mon - 1]}-{year}.txt"
