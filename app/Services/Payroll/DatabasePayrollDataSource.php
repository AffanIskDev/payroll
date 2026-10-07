<?php

namespace App\Services\Payroll;

use App\Models\AttendanceLog;
use App\Models\EmployeeLoan;
use App\Models\KpiScore;
use App\Models\OvertimeRecord;
use App\Services\Payroll\Contracts\PayrollDataSource;
use Carbon\CarbonInterface;

/** Membaca sumber data payroll dari tabel lokal (salinan data Rumatku & ROSY). */
class DatabasePayrollDataSource implements PayrollDataSource
{
    public function attendanceSummary(int $employeeId, CarbonInterface $start, CarbonInterface $end): array
    {
        $logs = AttendanceLog::query()
            ->where('employee_id', $employeeId)
            ->whereBetween('work_date', [$start->toDateString(), $end->toDateString()])
            ->get(['status', 'late_minutes']);

        return [
            'attended_days' => $logs->where('status', 'HADIR')->count(),
            'leave_sick_days' => $logs->whereIn('status', ['IZIN', 'SAKIT', 'CUTI'])->count(),
            'absent_days' => $logs->where('status', 'ALPA')->count(),
            'late_minutes' => $logs->where('status', 'HADIR')->pluck('late_minutes')
                ->map(fn ($m) => (int) $m)->values()->all(),
        ];
    }

    public function lateMinutes(int $employeeId, CarbonInterface $start, CarbonInterface $end): array
    {
        return $this->attendanceSummary($employeeId, $start, $end)['late_minutes'];
    }

    public function approvedOvertimeHours(int $employeeId, CarbonInterface $start, CarbonInterface $end): float
    {
        return round((float) OvertimeRecord::query()
            ->where('employee_id', $employeeId)
            ->where('status', 'APPROVED')
            ->whereBetween('work_date', [$start->toDateString(), $end->toDateString()])
            ->sum('hours'), 2);
    }

    public function kpiScore(int $employeeId, string $periodCode): ?array
    {
        $kpi = KpiScore::query()->where('employee_id', $employeeId)->where('period_code', $periodCode)->first();

        return $kpi ? ['score' => (float) $kpi->score, 'incentive_amount' => $kpi->incentive_amount] : null;
    }

    public function loanInstallments(int $employeeId, string $periodCode): array
    {
        return EmployeeLoan::query()
            ->where('employee_id', $employeeId)
            ->where('is_active', true)
            ->get()
            ->filter(fn (EmployeeLoan $loan) => $loan->installmentNumberFor($periodCode) !== null)
            ->map(fn (EmployeeLoan $loan) => [
                'description' => $loan->description.' ('.$loan->installmentNumberFor($periodCode).'/'.$loan->installments_total.')',
                'amount' => $loan->installment_amount,
            ])
            ->values()
            ->all();
    }
}
