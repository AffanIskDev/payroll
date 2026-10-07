<?php

namespace App\Exports;

use Maatwebsite\Excel\Concerns\FromArray;
use Maatwebsite\Excel\Concerns\WithColumnWidths;
use Maatwebsite\Excel\Concerns\WithHeadings;
use Maatwebsite\Excel\Concerns\WithTitle;

/** Template unggah saldo awal pajak YTD dengan contoh FIKTIF (tidak memuat data pajak karyawan). */
class TaxInitialBalanceTemplateExport implements FromArray, WithColumnWidths, WithHeadings, WithTitle
{
    public function headings(): array
    {
        return [
            'employee_id / NIK', 'tax_year', 'cutoff_month', 'ptkp_status', 'gross_income_ytd',
            'employee_jht_jp_ytd', 'biaya_jabatan_ytd', 'pph21_paid_ytd', 'notes',
        ];
    }

    public function array(): array
    {
        $year = (int) date('Y');

        return [
            ['EMP-CONTOH-001', $year, 2, 'K/1', 18000000, 360000, 900000, 180000, 'CONTOH — hapus baris ini, isi dari sistem lama'],
            ['EMP-CONTOH-002', $year, 2, 'TK/0', 12000000, 240000, 600000, 60000, 'CONTOH — cut-off = bulan terakhir di sistem lama'],
        ];
    }

    public function columnWidths(): array
    {
        return ['A' => 20, 'B' => 10, 'C' => 13, 'D' => 12, 'E' => 18, 'F' => 20, 'G' => 18, 'H' => 16, 'I' => 40];
    }

    public function title(): string
    {
        return 'Saldo Awal YTD';
    }
}
