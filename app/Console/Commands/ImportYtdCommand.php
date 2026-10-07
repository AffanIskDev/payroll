<?php

namespace App\Console\Commands;

use App\Imports\EmployeeTaxInitialBalanceImport;
use Illuminate\Console\Command;
use Maatwebsite\Excel\Facades\Excel;
use Symfony\Component\Console\Helper\ProgressBar;

/** Modul 4A: php artisan payroll:import-ytd storage/app/saldo_awal.xlsx */
class ImportYtdCommand extends Command
{
    protected $signature = 'payroll:import-ytd
        {filepath : Path file .xlsx / .csv}
        {--dry-run : Hanya validasi, tidak menyimpan}
        {--strict : Batalkan seluruh impor bila ada satu baris pun yang gagal}';

    protected $description = 'Impor saldo awal pajak YTD (employee_tax_initial_balances) dari spreadsheet';

    public function handle(): int
    {
        $path = (string) $this->argument('filepath');
        $real = realpath($path) ?: realpath(base_path($path));
        if (! $real || ! is_file($real)) {
            $this->error("File tidak ditemukan: {$path}");

            return self::FAILURE;
        }

        $extension = strtolower(pathinfo($real, PATHINFO_EXTENSION));
        if (! in_array($extension, ['xlsx', 'xls', 'csv'], true)) {
            $this->error('Format harus .xlsx, .xls, atau .csv');

            return self::FAILURE;
        }

        $delimiter = $extension === 'csv' ? EmployeeTaxInitialBalanceImport::detectDelimiter($real) : ',';
        $bar = null;

        // Lintasan pertama: validasi seluruh baris dengan progress bar.
        $check = new EmployeeTaxInitialBalanceImport(
            dryRun: true,
            delimiter: $delimiter,
            onStart: function (int $total) use (&$bar) {
                $bar = new ProgressBar($this->output, $total);
                $bar->start();
            },
            onRow: fn () => $bar?->advance(),
        );
        Excel::import($check, $real);
        $bar?->finish();
        $this->newLine(2);

        $this->info("Total baris: {$check->total} • lolos validasi: ".count($check->valid).' • gagal: '.count($check->errors));

        if ($check->errors) {
            $this->warn('Ringkasan error:');
            $this->table(['Baris', 'NIK', 'Masalah'], array_map(
                fn (array $e) => [$e['row'], $e['nik'] ?: '-', implode(' ', $e['messages'])],
                $check->errors,
            ));
        }
        foreach ($check->warnings as $w) {
            $this->line("<comment>Peringatan baris {$w['row']} ({$w['nik']}):</comment> {$w['message']}");
        }

        if ($this->option('dry-run')) {
            $this->comment('Mode --dry-run: tidak ada data yang disimpan.');

            return $check->errors ? self::FAILURE : self::SUCCESS;
        }

        if ($check->errors && $this->option('strict')) {
            $this->error('Mode --strict: impor dibatalkan karena ada baris yang gagal.');

            return self::FAILURE;
        }

        if (! $check->valid) {
            $this->error('Tidak ada baris valid untuk disimpan.');

            return self::FAILURE;
        }

        $save = new EmployeeTaxInitialBalanceImport(dryRun: false, delimiter: $delimiter);
        Excel::import($save, $real);
        $this->info("Tersimpan: {$save->saved} saldo awal (updateOrCreate per NIK + tahun pajak).");

        return $check->errors ? self::FAILURE : self::SUCCESS;
    }
}
