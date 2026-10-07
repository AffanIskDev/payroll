<?php

namespace App\Services\Payroll;

use App\Jobs\GeneratePayslipPdfJob;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\PayslipAdjustment;
use App\Models\User;
use App\Notifications\PayslipPublishedNotification;
use App\Support\Money;
use DomainException;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;

/**
 * Siklus hidup slip (PRD langkah 5–6): Approve & Lock → render PDF (queue) →
 * PUBLISHED dan notifikasi ke karyawan di Rumatku.
 *
 * Sebelum dikunci, slip selalu dihitung ulang dengan data terkini sehingga angka
 * yang dibekukan = angka yang tampil di workbench, lalu diperiksa penjaganya
 * (THP negatif, urutan masa pajak terakhir, saldo awal YTD tumpang tindih).
 */
class PayslipApprovalService
{
    public function __construct(private readonly PayrollPipelineService $pipeline) {}

    public function lock(Payslip $payslip, User $manager): void
    {
        $payslip->loadMissing('period');
        if ($payslip->period->isGenerating()) {
            throw new DomainException('Batch payroll sedang diproses. Tunggu sampai selesai sebelum approve.');
        }
        if (! $payslip->isDraft()) {
            return;
        }

        DB::transaction(function () use (&$payslip, $manager) {
            $payslip = $this->pipeline->refreshDraft($payslip, $manager->id);
            if ($reason = $this->blockingReason($payslip)) {
                throw new DomainException("{$payslip->employee_name}: {$reason}");
            }

            $this->markLocked(collect([$payslip->id]), $manager, 'Approve & Lock');
            $this->afterLock($payslip->period, $manager);
        });

        GeneratePayslipPdfJob::dispatch($payslip->id)->afterCommit();
    }

    /**
     * Approve & Lock semua slip draft yang lolos penjaga; sisanya tetap draft.
     *
     * @return array{locked: int, skipped: array<string, string>}
     */
    public function lockAll(PayrollPeriod $period, User $manager): array
    {
        if ($period->isGenerating()) {
            throw new DomainException('Batch payroll sedang diproses. Tunggu sampai selesai sebelum approve.');
        }

        $locked = collect();
        $skipped = [];

        DB::transaction(function () use ($period, $manager, $locked, &$skipped) {
            $drafts = $period->payslips()->where('status', Payslip::STATUS_DRAFT)
                ->with(['period', 'employee.salaryProfile'])->orderBy('employee_name')->get();

            foreach ($drafts as $slip) {
                $slip = $this->pipeline->refreshDraft($slip, $manager->id);
                if ($reason = $this->blockingReason($slip)) {
                    $skipped[$slip->employee_name] = $reason;

                    continue;
                }
                $locked->push($slip->id);
            }

            if ($locked->isNotEmpty()) {
                $this->markLocked($locked, $manager, 'Approve & Lock (massal)');
                $this->afterLock($period, $manager);
            }
        });

        foreach ($locked as $id) {
            GeneratePayslipPdfJob::dispatch($id)->afterCommit();
        }

        return ['locked' => $locked->count(), 'skipped' => $skipped];
    }

    /** Alasan slip belum boleh dikunci, atau null bila aman. */
    public function blockingReason(Payslip $payslip): ?string
    {
        $payslip->loadMissing('period');

        if ($payslip->take_home_pay < 0) {
            return 'THP negatif ('.Money::rupiah($payslip->take_home_pay).'). Kurangi potongan/kasbon sebelum approve.';
        }

        if ($payslip->pph21_method === 'PASAL17') {
            $draftMonths = Payslip::query()
                ->where('employee_id', $payslip->employee_id)
                ->whereKeyNot($payslip->id)
                ->where('status', Payslip::STATUS_DRAFT)
                ->whereHas('period', fn ($q) => $q->whereYear('start_date', $payslip->period->year())
                    ->where('start_date', '<', $payslip->period->start_date->toDateString()))
                ->with('period:id,period_name,start_date')
                ->get()
                ->sortBy(fn (Payslip $s) => $s->period->start_date)
                ->map(fn (Payslip $s) => $s->period->period_name);

            if ($draftMonths->isNotEmpty()) {
                return 'Masa pajak terakhir menunggu slip '.$draftMonths->implode(', ').' (masih draft) dikunci lebih dulu.';
            }

            $warnings = $payslip->pph21_breakdown['warnings'] ?? [];
            if ($warnings) {
                return 'Rekonsiliasi PPh 21 bermasalah: '.implode(' ', $warnings);
            }
        }

        return null;
    }

    /** Dipanggil job setelah PDF terenkripsi tersimpan. */
    public function publish(Payslip $payslip): void
    {
        if ($payslip->status !== Payslip::STATUS_LOCKED || ! $payslip->pdf_path) {
            return;
        }

        $payslip->forceFill([
            'status' => Payslip::STATUS_PUBLISHED,
            'published_at' => now(),
        ])->save();

        $payslip->loadMissing(['period', 'employee.user']);
        $payslip->period->refreshStatus();

        $payslip->employee->user?->notify(new PayslipPublishedNotification($payslip));
    }

    /** Buat ulang PDF untuk slip yang tertahan "locked" (mis. worker mati / render gagal). */
    public function retryPendingPdfs(PayrollPeriod $period): int
    {
        $ids = $period->payslips()->where('status', Payslip::STATUS_LOCKED)->pluck('id');
        foreach ($ids as $id) {
            GeneratePayslipPdfJob::dispatch($id);
        }

        return $ids->count();
    }

    public function close(PayrollPeriod $period, User $manager): void
    {
        if ($period->status !== PayrollPeriod::STATUS_PUBLISHED) {
            throw new DomainException('Periode hanya bisa ditutup setelah semua slip published.');
        }

        $period->forceFill(['status' => PayrollPeriod::STATUS_CLOSED, 'closed_at' => now()])->save();
    }

    /** @param Collection<int, int> $ids */
    private function markLocked(Collection $ids, User $manager, string $reason): void
    {
        Payslip::query()->whereKey($ids)->update([
            'status' => Payslip::STATUS_LOCKED,
            'locked_at' => now(),
            'locked_by' => $manager->id,
            'updated_at' => now(),
        ]);

        PayslipAdjustment::insert($ids->map(fn ($id) => [
            'payslip_id' => $id,
            'user_id' => $manager->id,
            'field' => 'status',
            'old_value' => Payslip::STATUS_DRAFT,
            'new_value' => Payslip::STATUS_LOCKED,
            'reason' => $reason,
            'created_at' => now(),
        ])->all());
    }

    private function afterLock(PayrollPeriod $period, User $manager): void
    {
        $period->refreshStatus();
        if (! $period->isDraft() && $period->approved_at === null) {
            $period->forceFill(['approved_by' => $manager->id, 'approved_at' => now()])->save();
        }
    }
}
