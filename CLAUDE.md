# RASA (PAYROLL-SINGKAT) — setup lokal

RASA = aplikasi gaji HRD RUMAT: backend FastAPI + MongoDB, frontend React (CRA + craco). Karyawan, presensi,
lembur, dan **login** diambil dari **HAM ROSY** lewat `api/ham/v2/payroll-feed/*` (hanya-baca). Branch kerja: `rasa`.
Langkah di bawah sudah diuji di instalasi bersih (13 Okt 2026) — ikuti apa adanya, tidak perlu menjelajah ulang.

## Yang perlu terpasang
| Alat | Versi teruji | Untuk |
|---|---|---|
| Python | 3.12 | backend |
| Node + Yarn 1 | Node 20, Yarn 1.22.22 (`corepack enable`) | frontend |
| MongoDB | 8.0 | DB RASA di `127.0.0.1:27017` |
| PHP + Composer | PHP 8.1, Composer 2 | HAM lokal (login & data) |
| MySQL | 8.0 | salinan DB `rosy-db-ham` + `rumatku` untuk HAM |

## Backend — port 8070
```bash
cd backend
python3.12 -m venv .venv
# emergentintegrations & litellm = paket privat Emergent: tidak dipakai kode dan tidak ada di PyPI, jadi dilewati
.venv/bin/pip install -r <(grep -vE '^(emergentintegrations|litellm)' requirements.txt)
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8070
```
`backend/.env` (di-gitignore, buat sendiri):
```
MONGO_URL=mongodb://127.0.0.1:27017
DB_NAME=rasa
JWT_SECRET=<acak: openssl rand -hex 32>
HAM_API_URL=http://127.0.0.1:8601
HAM_INTEGRASI_KEY=<sama persis dengan INTEGRASI_RASA_SECRET di .env HAM, minimal 24 karakter>
PAYROLL_COMPANY_ID=CP-001
CORS_ORIGINS=http://localhost:3070
```
Jangan isi `RUMATKU_API_URL` di lokal: kosong = pengiriman slip ke aplikasi RUMATKU hanya disimulasikan.

## Frontend — port 3070
```bash
cd frontend && yarn install && yarn start
```
`frontend/.env`:
```
REACT_APP_BACKEND_URL=http://localhost:8070
PORT=3070
BROWSER=none
DISABLE_EMERGENT_OVERLAY=true
```
Buka **http://localhost:3070** — bukan `127.0.0.1`, karena CORS hanya mengizinkan `localhost:3070`.

## HAM lokal — port 8601, wajib untuk login
Tanpa HAM, login selalu gagal (tidak ada akun lokal atau mode tester); tes unit tetap bisa jalan.
- Repo `IT-RUMAT/API-Service-Human-Capital`, branch `lembur-20261008` (memuat payroll-feed RASA, commit `72718d8`).
- `composer install`, salin `.env.example` → `.env`, lalu isi: `DB_HOST=127.0.0.1`, `DB_DATABASE=rosy-db-ham`,
  `DB_RUMATKU_DATABASE=rumatku`, `INTEGRASI_RASA_SECRET=<kunci yang sama dengan RASA>`, `PAYROLL_FEED_COMPANIES=CP-001`.
- Jalankan: `PHP_CLI_SERVER_WORKERS=4 php -S 127.0.0.1:8601 -t public`
- Salinan DB `rosy-db-ham` & `rumatku`: minta dump ke Affan. **Jangan arahkan HAM atau RASA ke DB production
  (`8.215.81.103`).**
- Login memakai akun ROSY berjabatan Manager HRD / Supervisor HRD yang ada di salinan DB itu. Data periode
  ditarik lewat Payroll → Periode Baru / tombol **Fetch Data Terbaru**.

## Tes
```bash
cd backend && .venv/bin/python -m pytest tests -q \
  --ignore=tests/backend_test.py --ignore=tests/test_iter8_new_features.py --ignore=tests/test_iter9_integrations.py \
  --ignore=tests/test_iter10_delivery.py --ignore=tests/test_workflow_v7.py --ignore=tests/test_tax_and_bsi.py \
  --ignore=tests/test_1721a1_and_delete_period.py
```
Harus hijau semua (181 lulus per 13 Okt). Tujuh berkas yang di-ignore adalah tes integrasi Emergent lama yang login
dengan akun lokal (dihapus 9 Okt): **sudah gagal sejak sebelumnya, jangan diperbaiki**. Tes yang butuh MongoDB
otomatis di-skip bila Mongo mati.

## Peta kode
- `backend/engine.py` — hitung slip (PPh 21 TER/Pasal 17, BPJS, poin presensi & absensi, aturan PJUnit); fungsi murni
  · gaji tidak penuh (`engine.prorata`, user 15 Okt 2026): faktor = hari kerja di masa aktif ÷ `DEFAULT_WORK_DAYS` (25), maks 1.
  Masuk/keluar di tengah periode → gapok, jabatan & kehadiran × faktor; kembali dari cuti melahirkan di tengah periode → hanya
  kehadiran (hari kerja di luar cuti), gapok & jabatan penuh; cuti melahirkan sepanjang periode tetap gapok saja. Hari kerja =
  log HAM selain libur (alfa/izin/sakit tetap dihitung & tetap berpoin; poin/alfa = 1/25 nilai BULANAN, dibatasi nilai yang
  diprorata); tanpa log (direksi bebas presensi) = Senin–Sabtu. BPJS tidak diprorata. Slip menyimpan `prorata`.
- `backend/pipeline.py` susun slip dari data tersinkron · `integrations.py` feed HAM · `labels.py` label per jabatan (Bonus Threshold = PJ Unit)
- `backend/routes_hr.py` API utama · `routes_tax.py` saldo YTD, 1721-A1, ekspor BSI · `pdf_service.py` slip PDF ·
  `bank_batch.py` TXT Batch Payment BSI
- `backend/verify.py` + `routes_verify.py` — slip "ditandatangani" dengan QR per slip (bukan gambar tanda tangan). QR berisi
  `{alamat}/verifikasi/{kode}`; halaman publik `frontend/src/pages/Verify.jsx` (tanpa login, tanpa nominal gaji) memanggil
  `GET /api/verify/{kode}`. Alamat = setelan `SLIP_VERIFY_BASE_URL` (Konfigurasi), kosong = alamat frontend pertama di
  `CORS_ORIGINS`; QR dibekukan saat slip di-approve. Alamat itu harus bisa dibuka dari HP karyawan (bukan localhost).
  Saat di-approve slip juga mendapat nomor dokumen `doc_number` (`SG/RUMAT/2026/09/0001`, urutan per periode lewat
  `$inc` atomik `payroll_periods.doc_seq`, Lock & Approve urut NIK) yang dicetak di bawah judul PDF bersama tanggal terbit
  (draft: "DRAFT — belum disetujui"); halaman verifikasi menampilkan nomor, tanggal terbit, status penerbitan & persetujuan,
  dan waktu pemeriksaan. Slip yang di-approve sebelum fitur nomor tidak punya nomor (baris ID Dokumen disembunyikan).
- `frontend/src/pages/hr/*.jsx` — satu berkas per menu; `Workbench.jsx` = review slip per karyawan
- Komentar bertanggal (mis. "user 13 Oct 2026") = keputusan bisnis dari user; jangan diubah tanpa konfirmasi.

## Aturan tampilan (desain RUMAT, 14 Okt 2026) — wajib diikuti
RASA harus terasa satu keluarga dengan ROSY dan RUMATku. Detail token ada di `design_guidelines.json`; ringkasnya:
- **Warna**: hanya `brand-*` (teal RUMAT, `tailwind.config.js`) untuk primary, link, menu aktif, fokus. Jangan pakai `blue-*`/`indigo-*` atau hex baru di JSX.
- **Font**: Nunito Sans (file di `src/fonts`, tanpa Google Fonts). Angka & rupiah: kelas `.num` (tabular-nums), **bukan** monospace.
- **Ukuran teks** minimal `text-xs`. Huruf kapital semua hanya untuk header tabel.
- **Merah (`rose-*`) hanya untuk masalah** (poin denda, ditolak, gagal). Potongan rutin seperti BPJS, PPh, Total Potongan ditulis `slate-700`.
- **Tombol**: pakai komponen `Btn` di `components/common.jsx`. Satu baris aksi maksimal 3 gaya: primary, outline netral, bahaya. Tinggi minimal 40px.
- **Kartu & panel**: `rounded-xl`, `border-slate-200`, `shadow-sm`; pakai `Panel`, `SummaryCard`, `PageTitle` yang sudah ada, jangan membuat versi sendiri.
- **Logo**: ikon sementara di `HrLayout.jsx` dan `Login.jsx` (komentar `[LOGO RUMAT]`) diganti logo resmi saat filenya tersedia.
- **Kartu angka** (Dashboard, halaman periode): pakai `AccentBody`/`SummaryCard` dengan prop `accent` — garis warna di kiri + angka berwarna. Warna hanya untuk makna, **cukup 4**: `brand` informasi biasa, `emerald` baik/selesai, `amber` perlu dicek, `rose` masalah. Jangan menambah warna per jenis angka (pajak, BPJS, dll). Angka 0 otomatis abu-abu.
- **Menu**: warna teal medis `brand-700`, menu aktif putih. Sidebar kiri di layar ≥1024px (`HrLayout.jsx`), bar ikon di atas untuk tablet/HP. Satu elemen yang berubah bentuk, jadi `data-testid` menu tidak ganda. Menu baru cukup ditambahkan ke array `NAV`. Sidebar bisa diciutkan jadi ikon saja (tombol `sidebar-toggle`, pilihan disimpan di localStorage `rasa.menu.ciut`); lebarnya variabel CSS `--sidebar-w`, jadi elemen `fixed` di halaman memakai `lg:left-[var(--sidebar-w)]`.
