<?php

namespace App\Services\Payroll;

use App\Services\Payroll\Contracts\PayrollDataSource;
use App\Support\Money;
use Carbon\CarbonInterface;

/**
 * Penalti keterlambatan non-duplikasi (PRD 3.3, Modul 1B). Hanya memotong
 * Tunjangan Kehadiran, dengan basis pembagi standar hari kerja (25 hari).
 */
class LateDeductionService
{
    /** Rule A: terlambat >= 60 menit dalam sehari = 1 hari penalti. */
    public const RULE_A_MINUTES = 60;

    /** Rule B: setiap 3 kali terlambat >= 15 menit = 1 hari penalti. */
    public const RULE_B_MINUTES = 15;

    public const RULE_B_COUNT = 3;

    /** Rule C: setiap kelipatan penuh 60 menit akumulasi = 1 hari penalti. */
    public const RULE_C_MINUTES = 60;

    public function __construct(
        private readonly PayrollSettings $settings,
        private readonly PayrollDataSource $source,
    ) {}

    /**
     * @return array{penalty_days: int, deduction_amount: int, rule_applied: ?string, rule_a_days: int,
     *     rule_b_days: int, rule_c_days: int, late_minutes_total: int, late_count_15: int,
     *     late_days_60: int, work_days_basis: int}
     */
    public function calculatePenalty(int $employeeId, CarbonInterface $startDate, CarbonInterface $endDate, float $monthlyAttendanceAllowance): array
    {
        return $this->evaluate($this->source->lateMinutes($employeeId, $startDate, $endDate), $monthlyAttendanceAllowance);
    }

    /**
     * @param  list<int>  $lateMinutesPerDay  menit terlambat tiap hari hadir
     */
    public function evaluate(array $lateMinutesPerDay, int|float $monthlyAttendanceAllowance): array
    {
        $minutes = array_values(array_filter(array_map('intval', $lateMinutesPerDay), fn (int $m) => $m > 0));

        $total = array_sum($minutes);
        $daysOver60 = count(array_filter($minutes, fn (int $m) => $m >= self::RULE_A_MINUTES));
        $countOver15 = count(array_filter($minutes, fn (int $m) => $m >= self::RULE_B_MINUTES));

        $ruleA = $daysOver60;
        $ruleB = intdiv($countOver15, self::RULE_B_COUNT);
        $ruleC = intdiv($total, self::RULE_C_MINUTES);

        // Rule D: ambil penalti tertinggi saja, tidak dijumlahkan.
        $penaltyDays = max($ruleA, $ruleB, $ruleC);

        $allowance = Money::round($monthlyAttendanceAllowance);
        $workDays = max(1, $this->settings->int('DEFAULT_WORK_DAYS'));
        $deduction = min(Money::fraction($allowance, $penaltyDays, $workDays), $allowance);

        $applied = [];
        if ($penaltyDays > 0) {
            foreach (['A' => $ruleA, 'B' => $ruleB, 'C' => $ruleC] as $rule => $days) {
                if ($days === $penaltyDays) {
                    $applied[] = $rule;
                }
            }
        }

        return [
            'penalty_days' => $penaltyDays,
            'deduction_amount' => $deduction,
            'rule_applied' => $applied ? 'Rule '.implode(' & ', $applied) : null,
            'rule_a_days' => $ruleA,
            'rule_b_days' => $ruleB,
            'rule_c_days' => $ruleC,
            'late_minutes_total' => $total,
            'late_count_15' => $countOver15,
            'late_days_60' => $daysOver60,
            'work_days_basis' => $workDays,
        ];
    }
}
