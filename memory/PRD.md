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

## Implemented (2026-10-06, iteration 3)
- Bukti Potong 1721-A1 tahunan (HRD: /hr-manager/tax-forms + PDF; Karyawan: daftar di /me + PDF terenkripsi DDMMYY). Hanya slip approved + saldo awal YTD. Config COMPANY_NAME / COMPANY_NPWP (placeholder), field NPWP karyawan.
- Biaya jabatan dibatasi Rp 500rb × bulan kerja (Desember & 1721-A1).
- Hapus periode draft / pending_approval (tanpa slip approved). Testing iteration_3: 53/53 pass.

## Implemented (2026-10-06, iteration 4)
- Jadwal kerja & shift (collection work_schedules, menu Jadwal, editable): KANTOR_PUSAT (Sen–Jum 08–16, Sab 08–14), UNIT_2SHIFT (S1 07–15/Sab 07–13, S2 13–21/Sab 13–19), UNIT_MINGGU (Sen–Jum 08–16, Min 08–14). Per karyawan work_schedule_code. Menit telat/pulang cepat dihitung dari jadwal (shift otomatis = jam masuk terdekat, bisa dipilih manual); hari libur jadwal = tanpa denda. Config WORK_START/END dihapus. Testing iteration_4: 67/67 pass.

## Implemented (2026-10-06, iteration 5)
- Rotasi shift mingguan (collection shift_rotations, menu Rotasi, grid 4 minggu, tombol Selang-seling). Prioritas shift: manual HRD > rotasi > jam masuk terdekat.
- Impor rekap absensi Rumatku (CSV/XLSX: nik, tanggal, jam_masuk, jam_pulang, foto_masuk/pulang URL, lokasi_masuk/pulang) dengan deteksi shift otomatis; foto & lokasi tampil sebagai link di tabel absensi. Testing iteration_5: 78/78 pass.

## Implemented (2026-10-06, iteration 6)
- Rekap Shift Bulanan (GET /api/hr/shift-recap?month=YYYY-MM, menu Rekap Shift, ekspor CSV): hari per shift, masuk hari libur, total masuk, libur jadwal, cuti/izin, tanpa log per petugas. Galeri foto absen tidak dibuat (sudah ada di Rumatku).

## Implemented (2026-10-06, iteration 7)
- Dashboard: total setoran BPJS Kesehatan & BPJS TK (periode terbaru).
- Config: COMPANY_ADDRESS, PAYSLIP_SIGNATORY_NAME/TITLE (kop & tanda tangan slip PDF, alamat di 1721-A1), CSV_DELIMITER (, ; | tab) untuk semua ekspor/template CSV.
- Menu digabung: Pajak (tab Saldo Awal YTD + Bukti Potong 1721-A1), Jadwal-Shift (tab Jadwal Kerja + Rotasi Shift).
- Workflow approval: Staff HR (admin_payroll) proses & ajukan → Manager HRD approve atau tolak dengan alasan → status revisi kembali ke staff; riwayat review. Akun demo staff.hr@rumatku.id. Testing iteration_7: 103/103 pass.

## Implemented (2026-10-06, iteration 8)
- Notifikasi dashboard (GET /api/hr/notifications): Manager melihat draft diajukan; Staff melihat draft ditolak + alasan.
- UNIT_MINGGU jadi 2 shift: S1 Sen–Jum 07–15 + Sabtu 08–14; S2 Sen–Jum 13–21 + Minggu 08–14.
- Menu Rekap (tab Rekap Shift + Rekap Lembur, GET /api/hr/overtime-recap, ekspor CSV).
- Absensi: pencarian karyawan (combobox search). Karyawan: label "Rate Lembur (Rp / jam)" default 0 + kolom tabel. Testing iteration_8: pass.

## Backlog
- P2: Notifikasi email slip & bukti potong, impor CSV absensi
- P2: Ekspor CSV e-Bupot / Coretax
- P2: Impor CSV absensi, notifikasi email slip, queue background PDF

## Next tasks
Sprint 4 → Sprint 5.
