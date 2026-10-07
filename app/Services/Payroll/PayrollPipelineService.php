<?php

namespace App\Services\Payroll;

use App\Models\Employee;
use App\Models\EmployeeSalaryProfile;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\PayslipAdjustment;
use App\Services\Payroll\Contracts\PayrollDataSource;
use App\Support\Money;
use App\Support\Terbilang;
use DomainException;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\ValidationException;
use Throwable;

/**
 * Orkestrasi penggajian (Modul 2A): tarik data → hitung penalti, lembur, KPI,
 * BPJS, PPh 21 → simpan slip berstatus draft. Juga menghitung ulang satu slip
 * ketika Manager HRD mengubah kolom manual di workbench.
 */
class PayrollPipelineService
{
    public function __construct(
        private readonly PayrollDataSource $source,
        private readonly LateDeductionService $late,
        private readonly BpjsCalculatorService $bpjs,
        private readonly Pph21CalculatorService $pph21,
        private readonly KpiIncentiveResolver $kpi,
    ) {}

    /**
     * Generate (atau generate ulang) slip draft untuk seluruh peserta periode.
     * Slip yang sudah dikunci tidak disentuh; nilai manual Manager HRD dipertahankan.
     * Galat satu karyawan (mis. data master rusak) dicatat tanpa menghentikan batch.
     *
     * @param  callable(Employee): void|null  $progress
     * @return array<string, string> galat per karyawan: nama => pesan
     */
    public function generateMonthlyBatch(PayrollPeriod $period, ?callable $progress = null): array
    {
        if (! $period->isDraft()) {
            throw new DomainException("Periode {$period->period_name} sudah dikunci; tidak bisa generate ulang.");
        }

        $eligibleIds = [];
        $errors = [];
        Employee::query()->payrollEligibleFor($period)->with('salaryProfile')->orderBy('id')
            ->chunkById(100, function ($employees) use ($period, $progress, &$eligibleIds, &$errors) {
                foreach ($employees as $employee) {
                    $eligibleIds[] = $employee->id;
                    try {
                        $this->generateForEmployee($period, $employee);
                    } catch (Throwable $e) {
                        report($e);
                        $errors["{$employee->full_name} ({$employee->nik})"] = $e->getMessage();
                    }
                    if ($progress) {
                        $progress($employee);
                    }
                }
            });

        // Karyawan yang sudah tidak menjadi peserta periode ini: buang draft lamanya.
        $period->payslips()->where('status', Payslip::STATUS_DRAFT)
            ->whereNotIn('employee_id', $eligibleIds ?: [0])
            ->delete();

        return $errors;
    }

    public function generateForEmployee(PayrollPeriod $period, Employee $employee): Payslip
    {
        $payslip = Payslip::query()->firstOrNew([
            'payroll_period_id' => $period->id,
            'employee_id' => $employee->id,
        ]);

        if ($payslip->exists && ! $payslip->isDraft()) {
            return $payslip;
        }

        $profile = $employee->salaryProfile ?? throw new DomainException("{$employee->full_name} belum punya profil gaji.");
        $system = $this->collectSystemValues($period, $employee, $profile);
        $overrides = $payslip->overrides ?? [];

        $payslip->fill($this->compute($period, $employee, $profile, $system, $overrides, $payslip->id));
        $payslip->status = Payslip::STATUS_DRAFT;
        $payslip->save();

        return $payslip;
    }

    /**
     * Data Ingestion (PRD langkah 2) → nilai hasil hitung sistem.
     *
     * @return array<string, mixed>
     */
    public function collectSystemValues(PayrollPeriod $period, Employee $employee, EmployeeSalaryProfile $profile): array
    {
        $start = $period->start_date;
        $end = $period->end_date;

        $attendance = $this->source->attendanceSummary($employee->id, $start, $end);
        $late = $this->late->evaluate($attendance['late_minutes'], $profile->monthly_attendance_allowance);

        $overtimeHours = $this->source->approvedOvertimeHours($employee->id, $start, $end);
        $overtimeRate = $profile->overtime_hourly_rate;

        $kpi = $this->source->kpiScore($employee->id, $period->period_code);
        $loans = $this->source->loanInstallments($employee->id, $period->period_code);

        return [
            'attended_days' => $attendance['attended_days'],
            'leave_sick_days' => $attendance['leave_sick_days'],
            'absent_days' => $attendance['absent_days'],
            'late' => $late,
            'late_penalty_amount' => $late['deduction_amount'],
            'overtime_hours' => $overtimeHours,
            'overtime_rate' => $overtimeRate,
            'overtime_pay' => Money::round($overtimeHours * $overtimeRate),
            'kpi_score' => $kpi['score'] ?? null,
            'kpi_incentive' => $this->kpi->resolve($kpi),
            'additional_bonus' => 0,
            'other_deductions' => array_sum(array_column($loans, 'amount')),
            'other_deductions_note' => $loans ? implode('; ', array_column($loans, 'description')) : null,
            'ingested_at' => now()->toDateTimeString(),
        ];
    }

    /**
     * Hitung seluruh komponen slip dari profil gaji + nilai sistem + override.
     * Murni perhitungan: tidak menyimpan apa pun.
     *
     * @param  array<string, mixed>  $system
     * @param  array<string, int|float|null>  $overrides
     * @return array<string, mixed> atribut Payslip
     */
    public function compute(
        PayrollPeriod $period,
        Employee $employee,
        EmployeeSalaryProfile $profile,
        array $system,
        array $overrides,
        ?int $payslipId = null,
    ): array {
        $basic = $profile->basic_salary;
        $position = $profile->position_allowance;
        $attendanceAllowance = $profile->monthly_attendance_allowance;

        $values = [];
        foreach (array_keys(Payslip::OVERRIDABLE) as $key) {
            $values[$key] = (array_key_exists($key, $overrides) && $overrides[$key] !== null)
                ? Money::round($overrides[$key])
                : Money::round($system[$key] ?? 0);
        }
        // Penalti hanya memotong Tunjangan Kehadiran (PRD 3.3).
        $values['late_penalty_amount'] = min(max(0, $values['late_penalty_amount']), $attendanceAllowance);

        $bpjs = $this->bpjs->calculate($basic, $profile);

        // Bruto (PRD 3.5): pokok + tunj. tetap + tunj. kehadiran + tunj. BPJS + lembur + KPI + bonus.
        $gross = $basic + $position + $attendanceAllowance
            + $bpjs['tunjangan_bpjs_kes'] + $bpjs['tunjangan_bpjs_tk']
            + $values['overtime_pay'] + $values['kpi_incentive'] + $values['additional_bonus'];

        $tax = $this->pph21->calculateTaxForPeriod($period, $employee, $gross, $bpjs['employee_jht_jp'], $payslipId);

        $totalDeductions = $values['late_penalty_amount']
            + $bpjs['iuran_bpjs_kes_total'] + $bpjs['iuran_bpjs_tk_total']
            + $tax['amount'] + $values['other_deductions'];
        $thp = $gross - $totalDeductions;

        $late = $system['late'] ?? [];

        return [
            'employee_nik' => $employee->nik,
            'employee_name' => $employee->full_name,
            'department' => $employee->department,
            'position' => $employee->position,
            'employment_status' => $employee->employment_status,
            'ptkp_status' => $tax['ptkp_status'],
            'ter_category' => $tax['ter_category'],
            'ter_rate' => $tax['ter_rate_bp'] !== null ? $tax['ter_rate_bp'] / 100 : null,

            'basic_salary' => $basic,
            'position_allowance' => $position,
            'attendance_allowance' => $attendanceAllowance,
            'bpjs_kes_base_salary' => $bpjs['kes_base'],
            'bpjs_tk_base_salary' => $bpjs['tk_base'],
            'bpjs_jp_base_salary' => $bpjs['jp_base'],
            'jkk_rate' => $profile->jkk_rate,

            'attended_days' => (int) ($system['attended_days'] ?? 0),
            'leave_sick_days' => (int) ($system['leave_sick_days'] ?? 0),
            'absent_days' => (int) ($system['absent_days'] ?? 0),
            'late_minutes_total' => (int) ($late['late_minutes_total'] ?? 0),
            'late_count_15' => (int) ($late['late_count_15'] ?? 0),
            'late_days_60' => (int) ($late['late_days_60'] ?? 0),
            'late_penalty_days' => (int) ($late['penalty_days'] ?? 0),
            'late_penalty_rule' => $late['rule_applied'] ?? null,
            'late_penalty_amount' => $values['late_penalty_amount'],

            'overtime_hours' => (float) ($system['overtime_hours'] ?? 0),
            'overtime_rate' => Money::round($system['overtime_rate'] ?? $profile->overtime_hourly_rate),
            'overtime_pay' => $values['overtime_pay'],
            'kpi_score' => $system['kpi_score'] ?? null,
            'kpi_incentive' => $values['kpi_incentive'],
            'additional_bonus' => $values['additional_bonus'],
            'tunjangan_bpjs_kes' => $bpjs['tunjangan_bpjs_kes'],
            'tunjangan_bpjs_tk' => $bpjs['tunjangan_bpjs_tk'],
            'gross_earnings' => $gross,

            'iuran_bpjs_kes_total' => $bpjs['iuran_bpjs_kes_total'],
            'iuran_bpjs_tk_total' => $bpjs['iuran_bpjs_tk_total'],
            'employee_jht_jp' => $bpjs['employee_jht_jp'],
            'bpjs_breakdown' => $bpjs + [
                'has_bpjs_kes' => $profile->has_bpjs_kes,
                'has_jkk' => $profile->has_jkk,
                'has_jkm' => $profile->has_jkm,
                'has_jht' => $profile->has_jht,
                'has_jp' => $profile->has_jp,
            ],
            'pph21_amount' => $tax['amount'],
            'pph21_method' => $tax['method'],
            'pph21_breakdown' => $tax['breakdown'],
            'other_deductions' => $values['other_deductions'],
            'other_deductions_note' => $system['other_deductions_note'] ?? null,
            'total_deductions' => $totalDeductions,

            'take_home_pay' => $thp,
            'terbilang' => Terbilang::rupiah($thp),
            'bank_name' => $profile->bank_name,
            'bank_account_number' => $profile->bank_account_number,
            'bank_account_name' => $profile->bank_account_name ?: mb_strtoupper($employee->full_name),

            'system_values' => $system,
            'overrides' => $overrides ?: null,
            'is_manually_adjusted' => $this->hasEffectiveOverride($system, $overrides),
        ];
    }

    /**
     * Hitung ulang slip draft dengan data master, pengaturan, dan slip lain yang
     * TERKINI (nilai sistem hasil tarikan & override tetap). Dipanggil sebelum
     * Approve & Lock agar angka yang dikunci sama dengan yang tampil di workbench.
     */
    public function refreshDraft(Payslip $payslip, ?int $userId = null): Payslip
    {
        $payslip->loadMissing(['period', 'employee.salaryProfile']);
        if (! $payslip->isDraft()) {
            return $payslip;
        }

        $before = $payslip->take_home_pay;
        $payslip->fill($this->compute(
            $payslip->period,
            $payslip->employee,
            $payslip->employee->salaryProfile ?? throw new DomainException("{$payslip->employee_name} tidak lagi punya profil gaji."),
            $payslip->system_values ?? [],
            $payslip->overrides ?? [],
            $payslip->id,
        ));

        if ($payslip->isDirty()) {
            $payslip->save();
            if ($before !== $payslip->take_home_pay) {
                PayslipAdjustment::create([
                    'payslip_id' => $payslip->id,
                    'user_id' => $userId,
                    'field' => 'take_home_pay',
                    'old_value' => (string) $before,
                    'new_value' => (string) $payslip->take_home_pay,
                    'reason' => 'Dihitung ulang otomatis: data master / pengaturan / slip bulan lain berubah sejak slip dibuat',
                ]);
            }
        }

        return $payslip;
    }

    /**
     * Pratinjau hitung ulang tanpa menyimpan (dipakai workbench reaktif).
     *
     * @param  array<string, int|float|null>  $overrides
     */
    public function preview(Payslip $payslip, array $overrides): Payslip
    {
        $payslip->loadMissing(['period', 'employee.salaryProfile']);
        $merged = $this->mergeOverrides($payslip, $overrides);

        $preview = $payslip->replicate();
        $preview->forceFill($this->compute(
            $payslip->period,
            $payslip->employee,
            $payslip->employee->salaryProfile,
            $payslip->system_values ?? [],
            $merged,
            $payslip->id,
        ));
        $preview->setRelation('period', $payslip->period);
        $preview->setRelation('employee', $payslip->employee);

        return $preview;
    }

    /**
     * Modul 2A: hitung ulang angka turunan setelah Manager HRD mengubah kolom
     * manual (lembur, insentif, bonus, denda, kasbon) dan catat riwayatnya.
     *
     * @param  array<string, int|float|string|null>  $overrides
     */
    public function recalculateSinglePayslip(Payslip $payslip, array $overrides, int $managerUserId, ?string $reason = null): Payslip
    {
        $payslip->loadMissing(['period', 'employee.salaryProfile']);

        if (! $payslip->isDraft()) {
            throw new DomainException('Slip sudah dikunci dan tidak bisa diubah.');
        }

        $this->validateOverrides($payslip, $overrides);
        $merged = $this->mergeOverrides($payslip, $overrides);

        return DB::transaction(function () use ($payslip, $merged, $managerUserId, $reason) {
            $before = $payslip->only(array_keys(Payslip::OVERRIDABLE));

            $payslip->fill($this->compute(
                $payslip->period,
                $payslip->employee,
                $payslip->employee->salaryProfile,
                $payslip->system_values ?? [],
                $merged,
                $payslip->id,
            ));

            $changed = [];
            foreach (Payslip::OVERRIDABLE as $field => $label) {
                if ((int) $before[$field] !== (int) $payslip->{$field}) {
                    $changed[$field] = [$before[$field], $payslip->{$field}];
                }
            }

            if ($changed && blank($reason)) {
                throw ValidationException::withMessages([
                    'adjustmentNotes' => 'Alasan penyesuaian wajib diisi setiap kali nilai slip diubah.',
                ]);
            }

            if ($changed) {
                $payslip->adjustment_notes = trim($reason);
            }
            $payslip->save();

            foreach ($changed as $field => [$old, $new]) {
                PayslipAdjustment::create([
                    'payslip_id' => $payslip->id,
                    'user_id' => $managerUserId,
                    'field' => $field,
                    'old_value' => (string) $old,
                    'new_value' => (string) $new,
                    'reason' => $reason,
                ]);
            }

            return $payslip->refresh();
        });
    }

    /**
     * Gabungkan override lama dengan input baru. Nilai yang sama dengan hasil
     * sistem dikembalikan ke "otomatis" (override dihapus).
     *
     * @param  array<string, int|float|string|null>  $input
     * @return array<string, int>
     */
    private function mergeOverrides(Payslip $payslip, array $input): array
    {
        $system = $payslip->system_values ?? [];
        $merged = $payslip->overrides ?? [];

        foreach ($input as $key => $value) {
            if (! array_key_exists($key, Payslip::OVERRIDABLE)) {
                continue;
            }
            if ($value === null || $value === '') {
                unset($merged[$key]);

                continue;
            }
            $amount = Money::round($value);
            if ($amount === Money::round($system[$key] ?? 0)) {
                unset($merged[$key]);
            } else {
                $merged[$key] = $amount;
            }
        }

        return $merged;
    }

    /** @param array<string, mixed> $overrides */
    private function validateOverrides(Payslip $payslip, array $overrides): void
    {
        $errors = [];
        foreach ($overrides as $key => $value) {
            if (! array_key_exists($key, Payslip::OVERRIDABLE)) {
                $errors[$key] = "Kolom {$key} tidak boleh diubah manual.";

                continue;
            }
            if ($value === null || $value === '') {
                continue;
            }
            if (! is_numeric($value) || (float) $value < 0) {
                $errors[$key] = Payslip::OVERRIDABLE[$key].' harus berupa angka >= 0.';

                continue;
            }
            if ((float) $value > 10_000_000_000) {
                $errors[$key] = Payslip::OVERRIDABLE[$key].' terlalu besar.';
            }
        }

        $allowance = $payslip->employee->salaryProfile->monthly_attendance_allowance;
        if (isset($overrides['late_penalty_amount']) && is_numeric($overrides['late_penalty_amount'])
            && Money::round($overrides['late_penalty_amount']) > $allowance) {
            $errors['late_penalty_amount'] = 'Potongan keterlambatan tidak boleh melebihi Tunjangan Kehadiran ('
                .Money::rupiah($allowance).').';
        }

        if ($errors) {
            throw ValidationException::withMessages($errors);
        }
    }

    /**
     * @param  array<string, mixed>  $system
     * @param  array<string, mixed>  $overrides
     */
    private function hasEffectiveOverride(array $system, array $overrides): bool
    {
        foreach ($overrides as $key => $value) {
            if ($value !== null && Money::round($value) !== Money::round($system[$key] ?? 0)) {
                return true;
            }
        }

        return false;
    }
}
