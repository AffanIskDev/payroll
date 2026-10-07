<?php

namespace App\Models;

use App\Services\Payroll\PayrollSettings;
use Illuminate\Database\Eloquent\Model;

class PayrollConfig extends Model
{
    protected $fillable = ['config_key', 'config_value', 'description'];

    protected static function booted(): void
    {
        // Nilai yang di-cache PayrollSettings harus langsung mengikuti perubahan.
        $flush = fn () => app(PayrollSettings::class)->flush();
        static::saved($flush);
        static::deleted($flush);
    }

    /**
     * Parameter payroll yang dikenali aplikasi. Nilai regulasi (UMK, plafon
     * BPJS) wajib diperbarui tiap tahun lewat halaman Pengaturan.
     *
     * type: money | int | json | string | enum
     */
    public const DEFINITIONS = [
        'UMK_BEKASI_REGENCY' => [
            'label' => 'UMK Kabupaten Bekasi',
            'type' => 'money',
            'default' => '5938885',
            'description' => 'Batas bawah (floor) basis upah BPJS Kesehatan',
        ],
        'BPJS_KES_MAX_WAGE' => [
            'label' => 'Plafon upah BPJS Kesehatan',
            'type' => 'money',
            'default' => '12000000',
            'description' => 'Batas atas basis upah iuran BPJS Kesehatan',
        ],
        'BPJS_JP_MAX_WAGE' => [
            'label' => 'Plafon upah Jaminan Pensiun',
            'type' => 'money',
            'default' => '10547400',
            'description' => 'Batas atas basis upah iuran JP (BPJS Ketenagakerjaan)',
        ],
        'DEFAULT_WORK_DAYS' => [
            'label' => 'Standar hari kerja per bulan',
            'type' => 'int',
            'default' => '25',
            'description' => 'Pembagi penalti keterlambatan (PP 35/2021)',
        ],
        'KPI_INCENTIVE_TIERS' => [
            'label' => 'Konversi skor KPI ke insentif',
            'type' => 'json',
            'default' => '[{"min":90,"amount":500000},{"min":80,"amount":300000},{"min":70,"amount":150000}]',
            'description' => 'Skor >= min mendapat amount; dipakai bila ROSY tidak mengirim nominal',
        ],
        'COMPANY_NAME' => [
            'label' => 'Nama perusahaan (pemotong pajak)',
            'type' => 'string',
            'default' => 'PT Sinergi Sehat Bersama',
            'description' => 'Tampil di slip gaji dan Formulir 1721-A1',
        ],
        'COMPANY_NPWP' => [
            'label' => 'NPWP perusahaan',
            'type' => 'string',
            'default' => '01.234.567.8-431.000',
            'description' => 'Identitas pemotong pajak di Formulir 1721-A1',
        ],
        'COMPANY_ADDRESS' => [
            'label' => 'Alamat perusahaan',
            'type' => 'string',
            'default' => 'Jl. Raya Cikarang No. 1, Kabupaten Bekasi, Jawa Barat',
            'description' => 'Tampil di Formulir 1721-A1',
        ],
        'HR_MANAGER_NAME' => [
            'label' => 'Penandatangan slip (nama)',
            'type' => 'string',
            'default' => 'Siti Nurhaliza, S.Psi.',
            'description' => 'Kolom "Disetujui & Diproses oleh" di slip gaji',
        ],
        'HR_MANAGER_TITLE' => [
            'label' => 'Penandatangan slip (jabatan)',
            'type' => 'string',
            'default' => 'Manager HRD & Personalia',
            'description' => 'Jabatan penandatangan slip dan 1721-A1',
        ],
        'BSI_DEBIT_ACCOUNT' => [
            'label' => 'Rekening debet BSI perusahaan',
            'type' => 'string',
            'default' => '7001234567',
            'description' => 'Rekening giro operasional untuk file Bulk Payment BSI',
        ],
        'BSI_CSV_SEPARATOR' => [
            'label' => 'Pemisah kolom CSV BSI',
            'type' => 'enum',
            'options' => [',' => 'Koma (,)', '|' => 'Pipe (|)'],
            'default' => ',',
            'description' => 'Sesuaikan dengan format upload BSI Corporate',
        ],
    ];
}
