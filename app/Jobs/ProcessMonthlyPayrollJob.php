<?php

namespace App\Jobs;

use App\Models\Employee;
use App\Models\PayrollPeriod;
use App\Services\Payroll\PayrollPipelineService;
use Illuminate\Contracts\Queue\ShouldBeUnique;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Support\Str;
use Throwable;

/**
 * Generate batch payroll satu periode secara asinkron agar ribuan karyawan
 * bisa diproses tanpa timeout HTTP (Modul 2A butir 2).
 */
class ProcessMonthlyPayrollJob implements ShouldBeUnique, ShouldQueue
{
    use Queueable;

    public int $timeout = 3600;

    public int $tries = 1;

    public function __construct(public int $periodId) {}

    public function uniqueId(): string
    {
        return (string) $this->periodId;
    }

    public function handle(PayrollPipelineService $pipeline): void
    {
        $period = PayrollPeriod::findOrFail($this->periodId);

        $period->update([
            'generation_status' => 'running',
            'generation_total' => Employee::query()->payrollEligibleFor($period)->count(),
            'generation_processed' => 0,
            'generation_error' => null,
        ]);

        $processed = 0;
        $errors = $pipeline->generateMonthlyBatch($period, function () use ($period, &$processed) {
            $processed++;
            if ($processed % 5 === 0) {
                $period->forceFill(['generation_processed' => $processed])->saveQuietly();
            }
        });

        $period->update([
            'generation_status' => 'completed',
            'generation_processed' => $processed,
            'generation_error' => $errors
                ? Str::limit(count($errors).' karyawan gagal dihitung (slip lain tetap dibuat): '
                    .collect($errors)->map(fn ($msg, $who) => "{$who}: {$msg}")->implode('; '), 1000)
                : null,
            'generated_at' => now(),
        ]);
        $period->refreshStatus();
    }

    public function failed(?Throwable $exception): void
    {
        PayrollPeriod::query()->whereKey($this->periodId)->update([
            'generation_status' => 'failed',
            'generation_error' => Str::limit((string) $exception?->getMessage(), 1000),
        ]);
    }
}
