<?php

namespace App\Console\Commands;

use App\Jobs\ProcessMonthlyPayrollJob;
use App\Models\PayrollPeriod;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;

/**
 * PRD langkah 1 (Trigger Periode, tanggal akhir bulan): buat periode bila belum
 * ada lalu jalankan batch draft. Dijadwalkan di routes/console.php.
 *
 * php artisan payroll:generate 2026-10 --sync
 */
class GeneratePayrollCommand extends Command
{
    protected $signature = 'payroll:generate
        {period? : Kode periode YYYY-MM (bawaan: bulan berjalan)}
        {--sync : Jalankan langsung tanpa queue worker}
        {--force : Tetap jalankan walau status periode tercatat sedang generate (mis. setelah worker mati)}';

    protected $description = 'Buat periode payroll (bila belum ada) dan generate slip draft seluruh karyawan aktif';

    public function handle(): int
    {
        $code = (string) ($this->argument('period') ?: now()->format('Y-m'));
        if (! preg_match('/^\d{4}-(0[1-9]|1[0-2])$/', $code)) {
            $this->error('Format periode harus YYYY-MM, mis. 2026-10.');

            return self::FAILURE;
        }

        $month = Carbon::createFromFormat('Y-m-d', $code.'-01');
        $period = PayrollPeriod::firstWhere('period_code', $code)
            ?? PayrollPeriod::createForMonth($month->year, $month->month);

        if (! $period->isDraft()) {
            $this->error("Periode {$period->period_name} sudah {$period->statusLabel()}; tidak bisa digenerate ulang.");

            return self::FAILURE;
        }
        if ($period->isGenerating() && ! $this->option('force')) {
            $this->warn("Generate periode {$period->period_name} sedang berjalan. Pakai --force bila prosesnya sudah mati.");

            return self::SUCCESS;
        }

        $period->update(['generation_status' => 'queued', 'generation_processed' => 0, 'generation_error' => null]);

        if ($this->option('sync')) {
            ProcessMonthlyPayrollJob::dispatchSync($period->id);
            $period->refresh();
            $this->info("Periode {$period->period_name}: {$period->generation_processed} karyawan diproses.");
            if ($period->generation_error) {
                $this->warn($period->generation_error);
            }
        } else {
            ProcessMonthlyPayrollJob::dispatch($period->id);
            $this->info("Periode {$period->period_name}: generate masuk antrean (pastikan queue worker berjalan).");
        }

        return self::SUCCESS;
    }
}
