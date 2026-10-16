"""Batch Payment BSI (bank_batch + POST /api/hr/periods/{pid}/export-batch-bsi, user request 10 Oct 2026): the TXT must
be the file ROSY HAM makes (PayrollModules::exportBatchPayment). Pure unit tests, plus one run of the endpoint against
a throwaway MongoDB database that is dropped afterwards (skipped when MongoDB is not running)."""
import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from bank_batch import approval_blockers, build, clean, file_name, row_problems  # noqa: E402

HEADER_LINE = ("0|BENEFICIARY ACCT (35)|BENEFICIARY ACCT NAME |CREDIT AMOUNT CCY|AMOUNT|CUST REF NO|MESSAGE (65)|"
               "EXTENDED PAYMENT DETAIL|BENEFICIARY NOTIF EMAIL(100)|SMS NOTIF (100)|")


def _emp(eid, name, acct="7123456789", code="BSI", bank="Bank Syariah Indonesia", acct_name=None):
    # Nama di Rekening is required since 14 Oct 2026 (user): filled in with the employee's name unless a test says otherwise
    return {"id": eid, "name": name, "bank_code": code, "bank_name": bank, "bank_account_number": acct,
            "bank_account_name": name if acct_name is None else acct_name}


def _slip(eid, name, thp, nik=None, payroll_status="active", status="approved"):
    return {"employee_id": eid, "employee": {"id": eid, "nik": nik or f"NIK-{eid}", "name": name},
            "take_home_pay": thp, "payroll_status": payroll_status, "status": status}


def _rows(text):
    return [line.split("|") for line in text.split("\r\n") if line.startswith("1|")]


# ---------------------------------------------------------------- layout
def test_file_is_byte_for_byte_the_rosy_layout():
    emps = {"e1": _emp("e1", "Budi Santoso", "7123456789"),
            "e2": _emp("e2", "Siti Aminah", "7198765432", acct_name="SITI AMINAH")}
    res = build([_slip("e2", "Siti Aminah", 4500000.0), _slip("e1", "Budi Santoso", 6000000.75)],
                emps, "2026-09", "2026-10-01")
    assert res["text"] == (
        "0|GAJI2609|2026-10-01|2|10500000|\r\n"
        + HEADER_LINE + "\r\n"
        "1|7123456789|Budi Santoso|IDR|6000000||GAJI SEPTEMBER 2026||||\r\n"
        "1|7198765432|SITI AMINAH|IDR|4500000||GAJI SEPTEMBER 2026||||")
    assert (res["count"], res["total"], res["skipped"], res["problems"]) == (2, 10500000, [], [])


def test_every_line_closes_with_a_pipe_and_the_last_line_has_no_line_break():
    res = build([_slip(f"e{i}", f"Nama {i}", 1000 * i) for i in range(1, 4)],
                {f"e{i}": _emp(f"e{i}", f"Nama {i}") for i in range(1, 4)}, "2026-12", "2027-01-02")
    lines = res["text"].split("\r\n")
    assert all(line.endswith("|") for line in lines)
    assert not res["text"].endswith(("\r\n", "\n")) and "\n" not in res["text"].replace("\r\n", "")
    assert lines[0] == "0|GAJI2612|2027-01-02|3|6000|"           # upload id from the payroll month
    assert {len(line.split("|")) for line in lines[1:]} == {11}  # data rows stay aligned with the header


def test_amount_is_rounded_down_and_the_total_is_the_sum_of_the_rows():
    res = build([_slip("a", "A", 1999.99), _slip("b", "B", 1.5)], {"a": _emp("a", "A"), "b": _emp("b", "B")},
                "2026-09", "2026-10-01")
    assert [r[4] for r in _rows(res["text"])] == ["1999", "1"]
    assert res["total"] == 2000 and res["text"].startswith("0|GAJI2609|2026-10-01|2|2000|")


# ---------------------------------------------------------------- rules (ROSY batchMasalahBaris)
@pytest.mark.parametrize("emp,kind", [
    (_emp("e", "X", code="BNI", bank="Bank Negara Indonesia"), "Bank bukan BSI"),
    (_emp("e", "X", code="", bank=""), "Bank bukan BSI"),
    (_emp("e", "X", acct=""), "Rekening kosong"),
    (_emp("e", "X", acct="   "), "Rekening kosong"),
    (_emp("e", "X", acct="712-345-678"), "Rekening bukan angka"),
    (_emp("e", "X", acct="71234 56789"), "Rekening bukan angka"),
    (_emp("e", "X", acct="٧١٢٣٤٥٦٧٨٩"), "Rekening bukan angka"),
    (_emp("e", "X", acct="76487"), "Panjang rekening ganjil"),
    (_emp("e", "X", acct="1"), "Panjang rekening ganjil"),
    (_emp("e", "X", acct="0000000000"), "Rekening nol semua"),
    (_emp("e", "X", acct_name=""), "Nama rekening kosong"),      # user 14 Oct 2026
    (_emp("e", "X", acct_name="   "), "Nama rekening kosong"),
])
def test_each_rosy_rule_blocks_the_row(emp, kind):
    assert [k for k, _ in row_problems(_slip("e", "X", 5000000), emp)] == [kind]


def test_a_bank_name_is_shown_and_an_unset_bank_says_so():
    assert row_problems(_slip("e", "X", 1), _emp("e", "X", code="BNI", bank="Bank Negara Indonesia"))[0][1] == \
        "Bank Negara Indonesia — harus dibayar lewat batch terpisah"
    assert row_problems(_slip("e", "X", 1), _emp("e", "X", code=None, bank=None))[0][1].startswith("bank belum diisi")


@pytest.mark.parametrize("thp,note", [(0, "Total Diterima = Rp 0"), (-150000, "Total Diterima = Rp -150.000")])
def test_zero_or_negative_pay_of_a_paid_employee_blocks(thp, note):
    assert row_problems(_slip("e", "X", thp), _emp("e", "X")) == [("Nominal tidak wajar", note)]


def test_an_employee_missing_from_rasa_blocks():
    assert row_problems(_slip("e", "X", 1), None)[0][0] == "Karyawan tidak ditemukan"


def test_one_bad_row_and_no_file_is_made_but_every_slip_is_reported():
    emps = {"a": _emp("a", "A"), "b": _emp("b", "B", acct="1"), "c": _emp("c", "C", code="BNI", bank="BNI", acct="")}
    res = build([_slip(x, x.upper(), 1000, nik=f"N{x}") for x in "cab"], emps, "2026-09", "2026-10-01")
    assert "text" not in res
    assert [(p["nik"], p["name"], p["kind"]) for p in res["problems"]] == [
        ("Nb", "B", "Panjang rekening ganjil"), ("Nc", "C", "Bank bukan BSI"), ("Nc", "C", "Rekening kosong")]


def test_unpaid_leave_rp0_slip_is_left_out_like_rosy_which_makes_no_slip():
    emps = {"a": _emp("a", "A"), "u": _emp("u", "U", acct="")}  # nothing to transfer, so no account needed either
    res = build([_slip("a", "A", 1000), _slip("u", "U", 0, nik="T2026", payroll_status="unpaid_leave")],
                emps, "2026-09", "2026-10-01")
    assert (res["count"], res["skipped"], [r[2] for r in _rows(res["text"])]) == (1, ["T2026"], ["A"])


def test_unpaid_leave_with_money_on_the_slip_is_still_paid():
    res = build([_slip("u", "U", 250000, payroll_status="unpaid_leave")], {"u": _emp("u", "U")}, "2026-09", "x")
    assert (res["count"], res["skipped"]) == (1, [])


# ---------------------------------------------------------------- name
def test_nama_di_rekening_is_written_as_is_and_required():
    """User 14 Oct 2026: an empty Nama di Rekening holds the row back; the employee's name is no longer used instead."""
    emps = {"a": _emp("a", "Muhammad Affan Iskandarsyah", acct_name="M Affan Iskandarsyah"),
            "b": _emp("b", "Dadang Suharto", acct_name="   ")}
    res = build([_slip("a", "Muhammad Affan Iskandarsyah", 1), _slip("b", "Dadang Suharto", 1, nik="N2")],
                emps, "2026-09", "x")
    assert res["problems"] == [{"nik": "N2", "name": "Dadang Suharto", "kind": "Nama rekening kosong",
                                "note": "Nama di Rekening belum diisi di ROSY"}]
    res = build([_slip("a", "Muhammad Affan Iskandarsyah", 1)], emps, "2026-09", "x")
    assert [r[2] for r in _rows(res["text"])] == ["M Affan Iskandarsyah"]


@pytest.mark.parametrize("raw,expected", [
    ("Baiq Riska Rahma Eprilya", "Baiq Riska Rahma Eprilya"),   # NBSP found in ROSY's real data
    ("Budi | Santoso", "Budi Santoso"),                               # a pipe would shift every later column
    ("Budi\r\nSantoso", "Budi Santoso"), ("Budi\tSantoso", "Budi Santoso"),
    ("﻿ Budi​  Santoso‍ ", "Budi Santoso"),
    (None, ""),
])
def test_clean_removes_what_breaks_a_pipe_file(raw, expected):
    assert clean(raw, 35) == expected


def test_a_long_name_is_cut_to_35_characters():
    name = "Ahmad Yudistira Pratama Nugraha Wijayakusuma"
    res = build([_slip("a", name, 1)], {"a": _emp("a", name)}, "2026-09", "x")
    assert _rows(res["text"])[0][2] == name[:35]


def test_file_name_matches_rosy():
    assert file_name({"id": "CP-001", "nama": "RUMAT"}, "2026-09") == "BatchPayment-RUMAT-September-2026.txt"
    assert file_name({"nama": "PT Rumah Perawatan Indonesia"}, "2026-12") == \
        "BatchPayment-PT-Rumah-Perawatan-Indonesia-Desember-2026.txt"
    assert file_name(None, "2026-01") == "BatchPayment-Januari-2026.txt"


# ---------------------------------------------------------------- Lock & Approve (user 14 Oct 2026)
def test_lock_and_approve_is_blocked_by_the_account_rules_only():
    emps = {"ok": _emp("ok", "Oke"), "nm": _emp("nm", "Nina", acct_name=""),
            "bni": _emp("bni", "Bayu", code="BNI", bank="Bank Negara Indonesia", acct="", acct_name=""),
            "zero": _emp("zero", "Zaki"), "u": _emp("u", "Umi", acct="", acct_name=""), "done": _emp("done", "Dewi", acct_name="")}
    res = approval_blockers([
        _slip("ok", "Oke", 1000, status="draft"), _slip("nm", "Nina", 1000, nik="N-nm", status="draft"),
        _slip("bni", "Bayu", 1000, nik="N-bni", status="draft"),
        _slip("zero", "Zaki", 0, status="draft"),                                 # Rp 0 is the slip's business
        _slip("u", "Umi", 0, status="draft", payroll_status="unpaid_leave"),      # nothing is transferred
        _slip("done", "Dewi", 1000, status="approved"),                           # already locked
        _slip("ghost", "Gita", 1000, nik="N-ghost", status="draft")], emps)       # not in RUSA's employees
    assert [(b["name"], [p["kind"] for p in b["problems"]]) for b in res] == [
        ("Bayu", ["Bank bukan BSI", "Rekening kosong", "Nama rekening kosong"]),
        ("Gita", ["Karyawan tidak ditemukan"]),
        ("Nina", ["Nama rekening kosong"])]
    assert {k: res[2][k] for k in ("employee_id", "nik", "bank", "account_number", "account_name")} == {
        "employee_id": "nm", "nik": "N-nm", "bank": "Bank Syariah Indonesia", "account_number": "7123456789",
        "account_name": ""}
    assert approval_blockers([_slip("ok", "Oke", 1000, status="draft")], emps) == []


# ---------------------------------------------------------------- endpoint
def test_export_is_manager_only():
    import routes_tax
    from core import require_manager
    assert any(d.dependency is require_manager for d in routes_tax.router.dependencies)
    assert "/api/hr/periods/{pid}/export-batch-bsi" in {r.path for r in routes_tax.router.routes}


def test_endpoint_against_a_throwaway_database(monkeypatch):
    from motor.motor_asyncio import AsyncIOMotorClient
    import pipeline
    import routes_tax

    name = f"rasa_test_batch_{uuid.uuid4().hex[:8]}"

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:  # noqa: BLE001
            client.close()
            pytest.skip("MongoDB lokal tidak berjalan")
        tdb = client[name]
        monkeypatch.setattr(routes_tax, "db", tdb)
        monkeypatch.setattr(pipeline, "db", tdb)
        try:
            await tdb.payroll_periods.insert_many([
                {"id": "p1", "period_name": "September 2026", "start_date": "2026-09-01", "end_date": "2026-09-30",
                 "status": "draft", "company": {"id": "CP-001", "nama": "RUMAT"}},
                {"id": "p0", "period_name": "Agustus 2026", "start_date": "2026-08-01", "end_date": "2026-08-31",
                 "status": "draft"}])
            await tdb.employees.insert_many([_emp("e1", "Budi Santoso"),
                                             _emp("e2", "Siti Aminah", "76487", acct_name="SITI AMINAH"),
                                             _emp("u", "Risa", acct="")])
            # draft slips are exported too, as in ROSY (user 10 Oct 2026)
            await tdb.payslips.insert_many([{**s, "payroll_period_id": "p1"} for s in (
                _slip("e1", "Budi Santoso", 6000000, nik="3201", status="draft"),
                _slip("e2", "Siti Aminah", 4500000, nik="3202"),
                _slip("u", "Risa", 0, nik="3203", payroll_status="unpaid_leave", status="draft"))])

            with pytest.raises(HTTPException) as e:
                await routes_tax.export_batch_bsi("p0")
            assert (e.value.status_code, e.value.detail) == (400, "Belum ada slip pada periode ini")

            r = await routes_tax.export_batch_bsi("p1")
            body = json.loads(r.body)
            assert r.status_code == 422 and body["slip_count"] == 3
            assert body["problems"] == [{"nik": "3202", "name": "Siti Aminah", "kind": "Panjang rekening ganjil",
                                         "note": "76487 = 5 digit, seharusnya 10"}]
            assert body["detail"] == "Berkas tidak dibuat: 1 data harus dibetulkan dulu"

            # the account is fixed in ROSY and synced: the slips are untouched, the file follows the master
            await tdb.employees.update_one({"id": "e2"}, {"$set": {"bank_account_number": "7198765432"}})
            r = await routes_tax.export_batch_bsi("p1")
            assert r.status_code == 200 and r.media_type == "text/plain"
            assert r.headers["content-type"] == "text/plain; charset=utf-8"
            assert r.headers["content-disposition"] == 'attachment; filename="BatchPayment-RUMAT-September-2026.txt"'
            assert (r.headers["x-exported-count"], r.headers["x-total-amount"], r.headers["x-skipped-niks"]) == \
                ("2", "10500000", "3203")
            lines = r.body.decode().split("\r\n")
            assert re.fullmatch(r"0\|GAJI2609\|\d{4}-\d{2}-\d{2}\|2\|10500000\|", lines[0])
            assert lines[1:] == [HEADER_LINE, "1|7123456789|Budi Santoso|IDR|6000000||GAJI SEPTEMBER 2026||||",
                                 "1|7198765432|SITI AMINAH|IDR|4500000||GAJI SEPTEMBER 2026||||"]
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(run())
