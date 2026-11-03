"""Karyawan & gaji yang diinput di RUSA (3 Nov 2026) — uji murni: tanpa server, tanpa database."""
import io
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rasa_unit")

import employees_rusa as er  # noqa: E402
import integrations  # noqa: E402
from engine import compute_payslip  # noqa: E402

CFG = {"UMK_BEKASI_REGENCY": "5219263", "BPJS_JP_MAX_WAGE": "10042300", "BPJS_KES_MAX_WAGE": "12000000",
       "DEFAULT_WORK_DAYS": "25"}
GOOD = {"nik": "2026101", "name": "Siti Aminah", "gender": "P", "ptkp_status": "TK/0", "basic_salary": "3.000.000",
        "position_allowance": 500000, "monthly_attendance_allowance": "1000000", "bpjs_kes": "Ya", "bpjs_tk": "Ya",
        "bank_code": "bsi", "bank_account_number": "7123 4567 89", "bank_account_name": "Siti Aminah"}


def _xlsx(rows, titles=None):
    wb = Workbook()
    ws = wb.active
    ws.append(titles or [t + (" *" if r else "") for _, t, r, _ in er.COLUMNS])
    keys = [k for k, *_ in er.COLUMNS]
    for r in rows:
        ws.append([r.get(k) for k in keys])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_a_good_row_is_cleaned_and_valid():
    row, errs = er.validate_row(GOOD)
    assert errs == []
    assert row["basic_salary"] == 3000000 and row["monthly_attendance_allowance"] == 1000000   # "3.000.000" = ribuan
    assert row["bank_code"] == "BSI" and row["bank_account_number"] == "7123456789"            # huruf besar, spasi dibuang
    assert row["is_paid"] is True and row["is_active"] is True and row["bpjs_kes"] is True


@pytest.mark.parametrize("patch,needle", [
    ({"nik": ""}, "NIK wajib"), ({"nik": "0"}, "NIK tidak boleh"), ({"name": " "}, "Nama wajib"),
    ({"gender": "X"}, "Jenis Kelamin"), ({"ptkp_status": "TK/9"}, "PTKP"), ({"basic_salary": 0}, "Gaji Pokok"),
    ({"basic_salary": "abc"}, "bukan angka"), ({"position_allowance": -1}, "negatif"),
    ({"join_date": "5 Januari"}, "YYYY-MM-DD"), ({"join_date": "2026-05-01", "exit_date": "2026-04-01"}, "Tgl Keluar"),
    ({"bpjs_kes": "mungkin"}, "Ya atau Tidak"), ({"bank_account_number": "12ab"}, "hanya boleh angka"),
    ({"bank_account_name": ""}, "Nama di Rekening"),
])
def test_each_rule_reports_a_clear_error(patch, needle):
    _, errs = er.validate_row({**GOOD, **patch})
    assert any(needle in e for e in errs), errs


def test_the_document_has_the_same_keys_as_a_rosy_employee_and_the_engine_pays_it():
    row, _ = er.validate_row(GOOD)
    doc = er.to_employee_doc(row)
    rosy = integrations.normalize_employee({"employee_id": "x", "nik": "1", "name": "n", "salary": {}, "bpjs": {}, "bank": {}})
    assert set(rosy) - {"rosy_employee_id"} <= set(doc)          # kunci ROSY semua ada
    assert "rosy_employee_id" not in doc and doc["attendance_exempt"] is True
    assert doc["has_bpjs_kes"] and doc["has_bpjs_tk"] and doc["bank_code"] == "BSI"
    slip = compute_payslip(doc, [], CFG, {})                     # tanpa log presensi: hadir penuh, tanpa potongan
    assert slip["basic_salary"] == 3000000 and slip["attendance_allowance"] == 1000000
    assert slip["presence_penalty_amount"] == 0 and slip["take_home_pay"] > 0


def test_unpaid_and_no_bpjs_are_carried_into_the_document():
    row, _ = er.validate_row({**GOOD, "is_paid": "Unpaid", "bpjs_kes": "Tidak", "bpjs_tk": "Tidak"})
    doc = er.to_employee_doc(row)
    assert doc["payroll_status"] == "unpaid_leave" and not doc["has_bpjs_kes"] and not doc["has_bpjs_tk"]


def test_workbook_columns_are_found_by_title_in_any_order_and_the_example_row_is_skipped():
    titles = ["Gaji Pokok *", "NIK *", "Nama *", "Jenis Kelamin (L/P) *", "PTKP *"]
    raw = _xlsx([], titles)
    wb = load_workbook(io.BytesIO(raw)); ws = wb.active
    ws.append([4000000, "7001", "Budi", "L", "K/1"])
    ws.append([3000000, "CONTOH-001", "Contoh Nama", "P", "TK/0"])    # baris contoh template
    buf = io.BytesIO(); wb.save(buf)
    parsed = er._parse_workbook(buf.getvalue())
    assert len(parsed) == 1 and parsed[0][1]["nik"] == "7001" and parsed[0][1]["name"] == "Budi"
    row, errs = er.validate_row(parsed[0][1])
    assert errs == [] and row["nik"] == "7001" and row["ptkp_status"] == "K/1"      # NIK angka Excel -> teks


def test_bad_files_are_refused_with_a_message():
    with pytest.raises(HTTPException) as e:
        er._parse_workbook(b"bukan excel")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        er._parse_workbook(_xlsx([], ["Foo", "Bar", "Baz", "Qux"]))
    assert "Baris judul" in e.value.detail
    with pytest.raises(HTTPException) as e:
        er._parse_workbook(_xlsx([], ["NIK", "Nama", "Jenis Kelamin (L/P)", "PTKP", "Tgl Lahir (YYYY-MM-DD)"]))
    assert "Gaji Pokok" in e.value.detail                              # kolom wajib hilang disebut


def test_the_template_round_trips_current_rusa_employees_without_changes():
    row, _ = er.validate_row({**GOOD, "department": "Pelayanan", "join_date": "2026-01-05"})
    emp = {**er.to_employee_doc(row), "id": "e1", "source": "rusa"}
    parsed = er._parse_workbook(er.build_template([emp]))
    assert len(parsed) == 1
    again, errs = er.validate_row(parsed[0][1])
    assert errs == []
    assert er.changes(again, emp) == []                                # unduh -> unggah apa adanya = "Sama"
    edited, _ = er.validate_row({**parsed[0][1], "basic_salary": 3500000})
    assert er.changes(edited, emp) == ["Gaji Pokok"]


def test_an_empty_template_has_one_example_row_and_a_guide_sheet():
    wb = load_workbook(io.BytesIO(er.build_template([])))
    assert [w.title for w in wb] == ["Karyawan", "Petunjuk"]
    assert wb["Karyawan"].cell(1, 1).value == "NIK *" and wb["Karyawan"].cell(2, 1).value == "CONTOH-001"


def test_rosy_feed_switch(monkeypatch):
    monkeypatch.delenv("ROSY_FEED_ENABLED", raising=False)
    assert integrations.rosy_enabled() is True
    for v in ("false", "0", "OFF"):
        monkeypatch.setenv("ROSY_FEED_ENABLED", v)
        assert integrations.rosy_enabled() is False
