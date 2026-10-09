import logging

from pymongo.errors import OperationFailure

from core import db, DEFAULT_CONFIGS
from integrations import LEAVE_MAP
from periods import BULAN, payroll_month, period_name_for
from schedules import seed_schedules

logger = logging.getLogger("seed")


async def migrate_employee_indexes():
    """HAM's nik is not unique (placeholders '-', '0'); employees are keyed by rosy_employee_id instead."""
    if (await db.employees.index_information()).get("nik_1", {}).get("unique"):
        await db.employees.drop_index("nik_1")
    await db.employees.create_index("nik")
    await db.employees.create_index("rosy_employee_id", unique=True, name="rosy_employee_id_unique",
                                    partialFilterExpression={"rosy_employee_id": {"$type": "string"}})


async def migrate_users():
    """Accounts are ROSY accounts (9 Oct 2026): local email/password users and the employee portal are gone."""
    if "email_1" in await db.users.index_information():
        await db.users.drop_index("email_1")
    await db.users.delete_many({"rosy_user_id": {"$exists": False}})
    await db.users.create_index("id", unique=True)
    await db.users.create_index("rosy_user_id", unique=True, name="rosy_user_id_unique",
                                partialFilterExpression={"rosy_user_id": {"$type": "string"}})


async def migrate_periods():
    """One period per month: every period carries its payroll month, guarded by a unique index."""
    async for p in db.payroll_periods.find({"bulan": {"$exists": False}}, {"_id": 0}):
        upd = {"bulan": payroll_month(p["start_date"])}
        # names typed before auto-naming lacked the year ("September") — a slip must show it
        if p["period_name"] in BULAN and period_name_for(p["start_date"], p["end_date"]):
            upd["period_name"] = period_name_for(p["start_date"], p["end_date"])
        await db.payroll_periods.update_one({"id": p["id"]}, {"$set": upd})
    try:
        await db.payroll_periods.create_index("bulan", unique=True, name="bulan_unique",
                                              partialFilterExpression={"bulan": {"$type": "string"}})
    except OperationFailure as e:
        logger.warning("Indeks unik bulan periode tidak dibuat (ada periode ganda di satu bulan): %s", e)


async def migrate_leave_types():
    """Logs keep HAM's status; re-derive leave_type so stored logs follow the current LEAVE_MAP (PPT rules)."""
    for status, lt in LEAVE_MAP.items():
        await db.attendance_daily_logs.update_many({"status_ham": status, "leave_type": {"$ne": lt}},
                                                   {"$set": {"leave_type": lt}})


async def seed():
    await migrate_users()
    await migrate_employee_indexes()
    await migrate_periods()
    await migrate_leave_types()
    await db.payslips.create_index([("payroll_period_id", 1), ("employee_id", 1)], unique=True)
    await db.attendance_daily_logs.create_index([("employee_id", 1), ("work_date", 1)], unique=True)
    await db.overtime_claims.create_index([("payroll_period_id", 1), ("employee_id", 1)])
    await db.period_components.create_index([("payroll_period_id", 1), ("employee_id", 1)])
    await db.login_attempts.create_index("identifier")
    # Kompensasi Denda Keterlambatan was removed; approved slips keep their history untouched
    await db.payslips.update_many({"status": {"$ne": "approved"}, "late_penalty_compensation": {"$exists": True}},
                                  {"$unset": {"late_penalty_compensation": ""}})
    for k, (v, desc) in DEFAULT_CONFIGS.items():
        await db.payroll_configs.update_one({"config_key": k}, {"$setOnInsert": {"config_key": k, "config_value": v},
                                                                "$set": {"description": desc}}, upsert=True)
    await db.payroll_configs.delete_many({"config_key": {"$nin": list(DEFAULT_CONFIGS)}})
    await seed_schedules()
    await db.employees.update_many({"work_schedule_code": {"$exists": False}},
                                   {"$set": {"work_schedule_code": "KANTOR_PUSAT"}})
