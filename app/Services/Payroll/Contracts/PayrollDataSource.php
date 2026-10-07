<?php

namespace App\Services\Payroll\Contracts;

use Carbon\CarbonInterface;

/**
 * Data Ingestion Service (PRD langkah 2): presensi & lembur dari Rumatku,
 * skor KPI dan kasbon dari ROSY. Ganti implementasinya untuk menarik data
 * langsung dari API Rumatku/ROSY tanpa mengubah mesin hitung.
 */
interface PayrollDataSource
{
    /**
     * @return array{attended_days: int, leave_sick_days: int, absent_days: int, late_minutes: list<int>}
     */
    public function attendanceSummary(int $employeeId, CarbonInterface $start, CarbonInterface $end): array;

    /** @return list<int> menit terlambat per hari hadir */
    public function lateMinutes(int $employeeId, CarbonInterface $start, CarbonInterface $end): array;

    public function approvedOvertimeHours(int $employeeId, CarbonInterface $start, CarbonInterface $end): float;

    /** @return array{score: float, incentive_amount: ?int}|null */
    public function kpiScore(int $employeeId, string $periodCode): ?array;

    /** @return list<array{description: string, amount: int}> */
    public function loanInstallments(int $employeeId, string $periodCode): array;
}
