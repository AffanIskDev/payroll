# ROSY Payroll × Rumatku — prototipe lokal

Implementasi **PRD Modul Payroll HRIS (ROSY) & Integrasi ESS (Rumatku) v1.0.0** beserta 10 prompt modul
(1A–5B) dari `Archive.zip`. Prototipe **mandiri di lokal**: tidak menyentuh repo ROSY, Rumatku, maupun server production.

| | |
|---|---|
| URL | http://127.0.0.1:8500 |
| Stack | Laravel 12 · PHP **8.3** (`php8.3`, bukan `php` default 8.1) · MySQL 8 lokal · Livewire 4 · Tailwind 4 · dompdf 3 + FPDI/TCPDF 6 · Laravel Excel 4 · Sanctum 4 |
| Database | `payroll_rosy_rumatku` (dev) · `payroll_rosy_rumatku_test` (tes) di `127.0.0.1:3306` |
| Tes | `php8.3 artisan test` → 90 tes / 420 asersi lulus |

## Menjalankan

Dua service systemd **user** sudah terpasang dan menyala otomatis saat login:

```bash
systemctl --user status  payroll-rosy-web payroll-rosy-queue   # cek
systemctl --user restart payroll-rosy-web payroll-rosy-queue   # setelah ubah kode
systemctl --user disable --now payroll-rosy-web payroll-rosy-queue   # matikan permanen
journalctl --user -u payroll-rosy-queue -f                     # log queue (generate & PDF)
```

Tanpa systemd (manual, dua terminal):

```bash
php8.3 artisan serve --host=127.0.0.1 --port=8500
php8.3 artisan queue:work --tries=3 --timeout=3600
```

Reset data demo (±45 detik, merender 72 PDF): `php8.3 artisan migrate:fresh --seed`
Build ulang aset setelah ubah tampilan: `npm run build`

### Akun demo (password semua: `password`)

| Peran | Email | Halaman awal |
|---|---|---|
| Manager HRD | `siti.nurhaliza@rosy.test` | Payroll (akses penuh) |
| Staff HRD | `rina.wulandari@rosy.test` | Presensi & Potongan (read-only, tanpa gaji manajemen) |
| Atasan Divisi | `hendra.gunawan@rosy.test` | KPI Tim (konfirmasi skor tim Pelayanan) |
| Karyawan | `budi.santoso@rosy.test` | Slip Gaji (password PDF `150390`) |

Semua 12 karyawan fiktif punya akun `nama.depan.nama.belakang@rosy.test`.

## Data demo

- Go-live sistem **Maret 2026**; saldo awal pajak Jan–Feb 2026 sudah "diimpor" (Modul 4A).
- Maret–Juli 2026 **ditutup**, Agustus **published**, September **draft — menunggu approval**.
- **Budi Santoso, Maret 2026 = `Visual Sample Slip Gaji Karyawan.pdf`**: Bruto Rp 9.914.400, potongan Rp 1.183.116,
  **THP Rp 8.731.284**, terbilang identik. Dikunci oleh tes otomatis.
- Kasus uji PRD ada di data: Dewi (pokok 4,5 jt < UMK → BPJS Kes pakai UMK), Andi Maret (telat 65 menit sekali → 1 hari,
  bukan 2), Joko (sering telat 16–25 menit → Rule B), Rudi (pokok 22 jt → plafon Kes & JP), Lina (tanpa JP).

## Alur demo 5 menit

1. Masuk sebagai **Manager HRD** → Payroll → **September 2026** → *Tinjau / Edit* Budi.
2. Ubah **Bonus Tambahan** → Bruto, PPh 21 TER, total potongan, THP, dan terbilang berubah seketika (Livewire).
3. *Simpan Draft* (alasan wajib) → riwayat penyesuaian tercatat → *Approve & Lock* → status
   "Terkunci - Memproses PDF" → beberapa detik kemudian **Published** (queue membuat PDF AES-128 ber-password).
4. Masuk sebagai **Budi** → Slip Gaji → notifikasi slip terbit → *Unduh PDF* → password `150390`.
5. Kembali sebagai Manager → *Export Transfer BSI* (CSV Bulk Payment), *Pajak → Bukti Potong 1721-A1*, *Impor Saldo Awal YTD*.

## API untuk Rumatku (PRD bab 7, Modul 3B & 5B)

```bash
B=http://127.0.0.1:8500/api/v1
T=$(curl -s -X POST $B/auth/token -d email=budi.santoso@rosy.test -d password=password | jq -r .data.access_token)
curl -s $B/employee/payslips            -H "Authorization: Bearer $T"     # riwayat slip published
curl -s $B/employee/payslips/4          -H "Authorization: Bearer $T"     # rincian (403 bila milik orang lain)
curl -s $B/employee/payslips/4/download -H "Authorization: Bearer $T" -o slip.pdf   # PDF terenkripsi DDMMYY
curl -s $B/employee/tax-documents/2026  -H "Authorization: Bearer $T"     # 1721-A1 (hanya bila tahun final)
```

Semua endpoint karyawan: `auth:sanctum` + `throttle:60,1`; respons galat selalu JSON.

## Peta modul → kode

| Modul | Isi | Lokasi utama |
|---|---|---|
| 1A Migrasi | 14 tabel + model Eloquent | `database/migrations/2026_10_06_2000*`, `app/Models` |
| 1B Core Engine | Penalti non-duplikasi, BPJS Full Gross + floor UMK, PPh 21 TER (tabel PP 58/2023, dicocokkan dengan `config_ter` ROSY) | `app/Services/Payroll/{LateDeduction,BpjsCalculator,Pph21TerCalculator}Service.php` |
| 2A Pipeline | Batch draft + job antrean + hitung ulang satu slip dengan jejak audit | `PayrollPipelineService`, `app/Jobs/ProcessMonthlyPayrollJob.php` |
| 2B Dashboard | Workbench reaktif `/hr-manager/payroll/{period}/employee/{employee}` | `app/Livewire/PayrollWorkbench.php` + view |
| 3A PDF | Template A4 meniru contoh slip, enkripsi AES-128 password DDMMYY, path `storage/app/payslips/{tahun}/{bulan}/{id}_{hash}.pdf` | `PayslipPdfService`, `PdfEncryptor`, `resources/views/pdf/payslip.blade.php` |
| 3B API Rumatku | `GET /api/v1/employee/payslips[/{id}[/download]]` | `app/Http/Controllers/Api/Employee/PayslipApiController.php` |
| 4A Saldo awal | Impor XLSX/CSV (validasi dulu, lalu simpan) + `php8.3 artisan payroll:import-ytd file.xlsx` | `app/Imports/EmployeeTaxInitialBalanceImport.php`, `ImportYtdCommand` |
| 4B Rekonsiliasi | Masa pajak terakhir (Desember / bulan resign) Pasal 17 UU HPP | `Pph21CalculatorService` |
| 5A CSV BSI | File Bulk Payment BSI + log ekspor | `BsiPayrollExportService` |
| 5B 1721-A1 | Formulir 22 baris, per orang / ZIP setahun, API karyawan | `TaxReport1721A1Service`, `resources/views/pdf/form_1721_a1.blade.php` |
| PRD langkah 1 | Trigger periode tiap akhir bulan: `php8.3 artisan payroll:generate [YYYY-MM] [--sync]` (terjadwal; butuh cron `schedule:run`) | `GeneratePayrollCommand`, `routes/console.php` |

Sumber data presensi/lembur (Rumatku) dan KPI/kasbon (ROSY) dibaca lewat antarmuka
`App\Services\Payroll\Contracts\PayrollDataSource`. Saat ini implementasinya tabel lokal; untuk integrasi cukup
mengganti binding di `AppServiceProvider` dengan adapter API.

## Keputusan & deviasi dari PRD (perlu dikonfirmasi PO)

| # | PRD / prompt modul | Yang dipakai | Alasan |
|---|---|---|---|
| 1 | Laravel 11.x | **Laravel 12** | 11.x (rilis terakhir 11.57) punya 4 advisory keamanan yang hanya ditambal di 12/13; struktur identik |
| 2 | Modul 1A: UMK 5.219.263, plafon JP 10.042.300 | PRD: **UMK 5.938.885**, JP **10.547.400**, plafon Kes 12 jt | PRD & contoh slip memakai nilai ini; semua bisa diubah di *Pengaturan* |
| 3 | Status PRD `DRAFT/LOCKED/PUBLISHED` vs Modul 1A `draft/pending_approval/approved/closed` | Slip: `draft → locked → published`; periode: `+ closed` | Mengikuti alur PRD bab 4; "approved/closed" Modul 3B = slip `published` |
| 4 | Rule B: PRD "≥3 kali → 1 hari" vs Modul 1B "setiap 3 kali" | **floor(jumlah/3)** (Modul 1B) | Lebih spesifik; untuk 3–5 kali hasilnya sama |
| 5 | Modul 1A `has_bpjs_tk` tunggal | Checklist per program (Kes/JKK/JKM/JHT/JP) | PRD 3.4 butir 4 |
| 6 | Konversi skor KPI → rupiah tidak didefinisikan | Tabel **≥90 = 500rb, ≥80 = 300rb, ≥70 = 150rb** (bisa diubah) | Mereproduksi contoh slip (92 poin → 500rb) |
| 7 | Enkripsi dompdf | **AES-128** via FPDI + TCPDF | Enkripsi dompdf hanya RC4 40-bit (kunci bisa dibobol tanpa password) |
| 8 | Biaya jabatan `min(5%, 6 jt)` | `min(5%, Rp500rb × bulan bekerja)` | Sama untuk setahun penuh; benar untuk karyawan resign/masuk tengah tahun |
| 9 | PPh Desember negatif "sesuai kebijakan" | Dikembalikan ke karyawan di slip masa terakhir (THP naik) | Ketentuan lebih potong pada masa pajak terakhir |
| 10 | 1721-A1 "Lambang Garuda / Judul" | **Judul saja** + catatan "dokumen pendamping; resmi via Coretax DJP" | Penggunaan lambang negara dibatasi; bukti potong resmi kini terbit dari Coretax |
| 11 | — | Karyawan hanya bisa mengunduh 1721-A1 **final**; versi sementara hanya untuk Manager (ditandai proyeksi) | Versi tengah tahun menampilkan lebih/kurang potong yang menyesatkan |
| 12 | — | Generate ulang **mempertahankan** nilai manual Manager; slip terkunci tidak tersentuh | Koreksi presensi tidak menghapus penyesuaian |
| 13 | — | Karyawan yang belum masuk / sudah resign sebelum periode tidak ikut batch | Mencegah gaji terbayar ke orang yang tidak bekerja |

## Pertanyaan terbuka untuk PO / konsultan pajak

1. **Perlakuan pajak "Full Gross"**: bruto memasukkan tunjangan JHT 3,7% + JP 2% porsi perusahaan, sedangkan pengurang
   tahunan hanya iuran **pekerja** (JHT 2% + JP 1%, sesuai PRD). Bila seluruh setoran 8,7% dianggap dibayar pekerja,
   PKP lebih kecil. Selisihnya ±5,7% × gaji pokok × 12 per karyawan per tahun → perlu putusan konsultan pajak.
2. **Potongan keterlambatan tidak mengurangi bruto pajak** (mengikuti contoh slip: TER × bruto penuh).
3. **Prorata gaji** karyawan masuk/keluar di tengah bulan belum diatur PRD (saat ini gaji penuh).
4. **Password PDF = tanggal lahir** hanya ±36.500 kemungkinan dan diketahui rekan/keluarga — layak dipertimbangkan PIN
   pilihan karyawan atau tautan sekali pakai di Rumatku.
5. **Format CSV BSI** mengikuti Modul 5A (8 kolom); cocokkan dengan format Batch Payment BSI yang sudah dipakai ROSY.

## Batasan prototipe

- Master karyawan, presensi, lembur, KPI, dan kasbon adalah data **fiktif** di tabel lokal (bukan tarikan ROSY/Rumatku).
- Notifikasi ke Rumatku tersimpan di tabel `notifications`; webhook dikirim hanya bila `RUMATKU_WEBHOOK_URL` diisi
  (payload ditandatangani HMAC di header `X-Rosy-Signature`).
- Token API diterbitkan lewat email+password ROSY untuk uji integrasi; di produksi sebaiknya lewat SSO Rumatku.
- Identitas perusahaan demo mengikuti contoh slip (PT Sinergi Sehat Bersama) — ubah di *Pengaturan*.
