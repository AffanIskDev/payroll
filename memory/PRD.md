# PRD — Payroll Otomatis ROSY & Rumatku

## Original problem statement
"buatkan saya aplikasi payroll otomatis dengan prd dan blueprint tersebut" — based on uploaded PRD_PAYROLL_ROSY_RUMATKU.md & master_blueprint_payroll_rosy_rumatku.md (Laravel/MySQL spec; implemented on platform stack React + FastAPI + MongoDB).
Follow-up: "saya tidak bisa masuk, tambahkan opsi tombol masuk sbg tester".

## Architecture
- Backend FastAPI: core.py (db, JWT auth, RBAC, rate limit 60/min employee API), engine.py (waterfall Rule1-4, BPJS + UMK floor, PTKP resolver, TER A/B/C, wage multiplier Pasal 93/STMB, terbilang), pipeline.py (batch/single recalc, approve & lock), pdf_service.py (reportlab + pypdf AES-256, password DDMMYY), routes_hr.py (/api/hr/*), routes_employee.py (/api/v1/employee/*), seed.py.
- Frontend React: /login (+ tester buttons), /hr-manager (dashboard, payroll, period detail, workbench, karyawan, absensi, konfigurasi), /me + /me/payslip/:id (mobile Rumatku).
- Collections: users, employees (salary profile), payroll_configs, attendance_daily_logs, payroll_periods, payslips, login_attempts.

## User personas
- Manager HRD / Admin Payroll (ROSY web): review, adjust, approve & lock.
- Karyawan (Rumatku mobile): clock-in/out, view & download encrypted slip.

## Core requirements (static)
Waterfall non-duplikasi denda (25 hari), leave matrix, BPJS basis gaji pokok + floor UMK Bekasi, bruto komersial vs bruto pajak TER, karyawati menikah TK/0, workbench 2 kolom editable amber + sticky THP terbilang, PDF DDMMYY, employee API.

## Implemented (2026-10-06)
- Full MVP above; seed demo data (Budi/Siti/Dimas, Maret 2026) — Budi 4 poin = Rp 160.000 verified.
- JWT auth (email or NIK), roles manager_hrd/admin_payroll/employee, brute-force lockout.
- Tester quick-login buttons (env DEMO_LOGIN_ENABLED="true"; set false before production).
- Testing agent iteration_1: 26/26 backend pass, frontend flows pass.

## Implemented (2026-10-06, iteration 2)
- Ekspor CSV transfer massal BSI (POST /api/hr/periods/{pid}/export-bsi, hanya slip approved; THP 0 / tanpa rekening dilewati). Rekening debet dari config BSI_COMPANY_DEBIT_ACCOUNT (placeholder).
- Impor saldo awal YTD (CSV , / ; atau .xlsx) di halaman Pajak YTD + template.
- Rekonsiliasi PPh 21 Desember Pasal 17 otomatis untuk periode yang berakhir di Desember (saldo YTD + slip sistem setelah cutoff + Desember). Testing iteration_2: 38/38 pass.

## Backlog
- P1: Bukti Potong 1721-A1 (Sprint 5)
- P2: Hapus periode draft (kebersihan data)
- P2: Impor CSV absensi, notifikasi email slip, queue background PDF

## Next tasks
Sprint 4 → Sprint 5.
