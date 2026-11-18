import logging

from pymongo.errors import OperationFailure

import accounts
from core import db, DEFAULT_CONFIGS, DEFAULT_COMPANIES, GLOBAL_COLLECTIONS, daftar_pt, dengan_pt, env_company, now_iso, semua_pt
from integrations import LEAVE_MAP
from periods import BULAN, payroll_month, period_name_for
from schedules import seed_schedules

logger = logging.getLogger("seed")


async def migrate_employee_indexes():
    """HAM's nik is not unique (placeholders '-', '0'); employees are keyed by rosy_employee_id instead."""
    if (await db.employees.index_information()).get("nik_1", {}).get("unique"):
        await db.employees.drop_index("nik_1")
    await db.employees.create_index([("company_id", 1), ("nik", 1)])
    # multi-PT: id karyawan ROSY unik PER PT — karyawan yang mutasi antar-PT punya id yang sama di dua PT
    if "rosy_employee_id_unique" in await db.employees.index_information():
        await db.employees.drop_index("rosy_employee_id_unique")
    await db.employees.create_index([("company_id", 1), ("rosy_employee_id", 1)], unique=True, name="pt_rosy_employee_id_unique",
                                    partialFilterExpression={"rosy_employee_id": {"$type": "string"}})
    # gaji diinput di RUSA (18 Nov 2026): satu baris gaji per karyawan ROSY per PT
    await db.gaji_karyawan.create_index([("company_id", 1), ("rosy_employee_id", 1)], unique=True, name="pt_gaji_rosy_employee_id")
    await db.gaji_karyawan_riwayat.create_index([("company_id", 1), ("rosy_employee_id", 1), ("at", -1)])
    await db.komponen_bulanan.create_index([("company_id", 1), ("bulan", 1), ("rosy_employee_id", 1), ("kode", 1)], unique=True,
                                           name="pt_komponen_bulanan")
    await db.komponen_bulanan_riwayat.create_index([("company_id", 1), ("bulan", 1), ("at", -1)])


async def migrate_users():
    """Akun & hak akses RUSA sendiri (3 Nov 2026) — lihat accounts.py."""
    await accounts.migrate_users()
    await accounts.ensure_master_admin()


async def migrate_periods():
    """One period per month: every period carries its payroll month, guarded by a unique index."""
    async for p in db.payroll_periods.find({"bulan": {"$exists": False}}, {"_id": 0}):
        upd = {"bulan": payroll_month(p["start_date"])}
        # names typed before auto-naming lacked the year ("September") — a slip must show it
        if p["period_name"] in BULAN and period_name_for(p["start_date"], p["end_date"]):
            upd["period_name"] = period_name_for(p["start_date"], p["end_date"])
        await db.payroll_periods.update_one({"id": p["id"]}, {"$set": upd})
    # periode lama = gaji; THR & Bonus Tahunan (user 30 Okt 2026) hidup di koleksi yang sama dengan run_type sendiri, jadi
    # keunikan per bulan berlaku per jenis run: satu gaji, satu THR, satu Bonus Tahunan per bulan
    await db.payroll_periods.update_many({"run_type": {"$exists": False}}, {"$set": {"run_type": "gaji"}})
    for lama in ("bulan_unique", "bulan_run_unique"):   # multi-PT: keunikan bulan berlaku per PT
        try:
            await db.payroll_periods.drop_index(lama)
        except OperationFailure:
            pass  # sudah diganti
    try:
        await db.payroll_periods.create_index([("company_id", 1), ("bulan", 1), ("run_type", 1)], unique=True,
                                              name="pt_bulan_run_unique", partialFilterExpression={"bulan": {"$type": "string"}})
    except OperationFailure as e:
        logger.warning("Indeks unik bulan periode tidak dibuat (ada periode ganda di satu bulan): %s", e)


async def migrate_leave_types():
    """Logs keep HAM's status; re-derive leave_type so stored logs follow the current LEAVE_MAP (PPT rules)."""
    for status, lt in LEAVE_MAP.items():
        await db.attendance_daily_logs.update_many({"status_ham": status, "leave_type": {"$ne": lt}},
                                                   {"$set": {"leave_type": lt}})


async def migrate_multi_pt():
    """Multi-PT (6 Nov 2026): satu DB untuk semua PT. PT bawaan dicatat di koleksi global `companies`; data lama (satu
    instance = satu PT) diberi company_id dari PAYROLL_COMPANY_ID. Idempoten — hanya menyentuh dokumen tanpa company_id."""
    for c in DEFAULT_COMPANIES:
        await db.companies.update_one({"id": c["id"]}, {"$setOnInsert": {**c, "is_active": True, "created_at": now_iso()}},
                                      upsert=True)
    lama = env_company()
    for name in await db.list_collection_names():
        if name in GLOBAL_COLLECTIONS or name.startswith("system."):
            continue
        res = await db[name].update_many({"company_id": {"$exists": False}}, {"$set": {"company_id": lama}})
        if res.modified_count:
            logger.info("multi-PT: %s dokumen %s diberi company_id %s", res.modified_count, name, lama)


async def seed():
    with semua_pt():   # migrasi lintas PT (tanpa saringan); seed per PT di bawah memakai dengan_pt()
        await migrate_multi_pt()
        await _seed_lintas_pt()
    for c in await daftar_pt(aktif_saja=False):
        with dengan_pt(c["id"]):
            await _seed_per_pt()


async def _seed_lintas_pt():
    await migrate_users()
    await migrate_employee_indexes()
    await migrate_periods()
    await migrate_leave_types()
    await db.payslips.create_index([("payroll_period_id", 1), ("employee_id", 1)], unique=True)
    # kode QR verifikasi slip (verify.py): dicari dari halaman publik, jadi harus unik & cepat; slip lama belum punya
    await db.payslips.create_index("verify_code", unique=True, sparse=True, name="verify_code_unique")
    # nomor dokumen slip (verify.py, 15 Okt 2026): dicetak di slip & halaman verifikasi, tidak boleh kembar
    await db.payslips.create_index("doc_number", unique=True, sparse=True, name="doc_number_unique")
    await db.attendance_daily_logs.create_index([("employee_id", 1), ("work_date", 1)], unique=True)
    await db.overtime_claims.create_index([("payroll_period_id", 1), ("employee_id", 1)])
    await db.period_components.create_index([("payroll_period_id", 1), ("employee_id", 1)])
    await db.login_attempts.create_index("identifier")
    # Kompensasi Denda Keterlambatan was removed; approved slips keep their history untouched
    await db.payslips.update_many({"status": {"$ne": "approved"}, "late_penalty_compensation": {"$exists": True}},
                                  {"$unset": {"late_penalty_compensation": ""}})
    await db.employees.update_many({"work_schedule_code": {"$exists": False}},
                                   {"$set": {"work_schedule_code": "KANTOR_PUSAT"}})


async def _seed_per_pt():
    """Konfigurasi & jadwal kerja bawaan untuk SETIAP PT (tiap PT punya UMK, rekening debet, dll. sendiri)."""
    for k, (v, desc) in DEFAULT_CONFIGS.items():
        await db.payroll_configs.update_one({"config_key": k}, {"$setOnInsert": {"config_key": k, "config_value": v},
                                                                "$set": {"description": desc}}, upsert=True)
    await db.payroll_configs.delete_many({"config_key": {"$nin": list(DEFAULT_CONFIGS)}})
    await seed_schedules()
