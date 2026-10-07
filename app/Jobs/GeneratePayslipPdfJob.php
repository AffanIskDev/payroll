<?php

namespace App\Jobs;

use App\Models\Payslip;
use App\Services\Payroll\PayslipApprovalService;
use App\Services\Payroll\PayslipPdfService;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Support\Str;
use Throwable;

/** Render PDF slip ber-password lalu publikasikan ke ESS (PRD langkah 5). */
class GeneratePayslipPdfJob implements ShouldQueue
{
    use Queueable;

    public int $tries = 3;

    public int $backoff = 10;

    public function __construct(public int $payslipId) {}

    public function handle(PayslipPdfService $pdf, PayslipApprovalService $approval): void
    {
        $payslip = Payslip::with(['period', 'employee'])->find($this->payslipId);

        if (! $payslip || $payslip->isDraft()) {
            return;
        }

        if ($payslip->status === Payslip::STATUS_LOCKED || ! $payslip->pdf_path) {
            $pdf->generate($payslip);
        }

        $approval->publish($payslip->refresh());
    }

    /** Slip tetap "locked" dan bisa dibuat ulang dari halaman periode. */
    public function failed(?Throwable $exception): void
    {
        Payslip::query()->whereKey($this->payslipId)->update([
            'pdf_error' => Str::limit((string) $exception?->getMessage(), 480),
        ]);
    }
}
