<?php

namespace App\Services\Payroll;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Support\Money;
use App\Support\Tanggal;
use Carbon\CarbonInterface;

/**
 * PPh 21 per masa pajak (Modul 4B):
 *  - Januari–November: TER bulanan (PP 58/2023).
 *  - Desember atau bulan karyawan resign: rekonsiliasi Pasal 17 UU HPP
 *    dengan saldo awal YTD (employee_tax_initial_balances) + slip sistem.
 */
class Pph21CalculatorService
{
    public const BIAYA_JABATAN_BP = 500; // 5%

    public const BIAYA_JABATAN_MAX_MONTHLY = 500_000;

    public const BIAYA_JABATAN_MAX_YEARLY = 6_000_000;

    /** Tarif progresif Pasal 17 ayat (1) huruf a UU HPP: [batas atas PKP, tarif bp]. */
    public const PASAL17_LAYERS = [
        [60_000_000, 500],
        [250_000_000, 1500],
        [500_000_000, 2500],
        [5_000_000_000, 3000],
        [null, 3500],
    ];

    public function __construct(private readonly Pph21TerCalculatorService $ter) {}

    /** Masa pajak terakhir: Desember, atau bulan karyawan berhenti bekerja. */
    public function isFinalTaxPeriod(PayrollPeriod $period, Employee $employee): bool
    {
        return $period->month() === 12 || $employee->resignsWithin($period);
    }

    /**
     * Status PTKP yang berlaku sepanjang tahun pajak = keadaan pada awal tahun pajak
     * (UU PPh Pasal 7 ayat 2). Perubahan di tengah tahun (menikah, anak lahir) baru
     * berlaku tahun berikutnya. Sumber berurutan: saldo awal YTD tahun itu → status
     * di slip pertama tahun itu → status di master karyawan (slip pertama / karyawan baru).
     */
    public function taxYearPtkpStatus(Employee $employee, int $year, ?CarbonInterface $before = null, ?int $excludePayslipId = null): string
    {
        $status = EmployeeTaxInitialBalance::query()
            ->where('employee_id', $employee->id)
            ->where('tax_year', $year)
            ->value('ptkp_status');

        $status ??= Payslip::query()
            ->join('payroll_periods', 'payroll_periods.id', '=', 'payslips.payroll_period_id')
            ->where('payslips.employee_id', $employee->id)
            ->when($excludePayslipId, fn ($q) => $q->where('payslips.id', '<>', $excludePayslipId))
            ->whereYear('payroll_periods.start_date', $year)
            ->when($before, fn ($q) => $q->where('payroll_periods.start_date', '<', $before->toDateString()))
            ->orderBy('payroll_periods.start_date')
            ->value('payslips.ptkp_status');

        return Pph21TerCalculatorService::normalizeStatus($status ?? $employee->ptkp_status);
    }

    /**
     * @param  int|null  $excludePayslipId  slip periode berjalan (kalau sudah tersimpan) agar tidak terhitung dua kali
     * @return array{method: string, amount: int, ptkp_status: string, ter_category: ?string, ter_rate_bp: ?int, breakdown: array<string, mixed>}
     */
    public function calculateTaxForPeriod(
        PayrollPeriod $period,
        Employee $employee,
        float $currentMonthGross,
        float $currentMonthJhtJp,
        ?int $excludePayslipId = null,
    ): array {
        $gross = Money::round($currentMonthGross);
        $status = $this->taxYearPtkpStatus($employee, $period->year(), $period->start_date, $excludePayslipId);

        if (! $this->isFinalTaxPeriod($period, $employee)) {
            $ter = $this->ter->calculate($gross, $status);

            return [
                'method' => 'TER',
                'amount' => $ter['amount'],
                'ptkp_status' => $status,
                'ter_category' => $ter['category'],
                'ter_rate_bp' => $ter['rate_bp'],
                'breakdown' => $ter,
            ];
        }

        $breakdown = $this->reconcile($period, $employee, $gross, Money::round($currentMonthJhtJp), $excludePayslipId, $status);

        return [
            'method' => 'PASAL17',
            'amount' => $breakdown['pph21_last_period'],
            'ptkp_status' => $status,
            'ter_category' => $this->ter->category($status),
            'ter_rate_bp' => null,
            'breakdown' => $breakdown,
        ];
    }

    /**
     * Rekonsiliasi akhir tahun. PPh 21 masa terakhir = PPh setahun − yang sudah
     * dipotong (saldo awal + TER Jan–Nov). Hasil negatif = lebih potong yang
     * dikembalikan ke karyawan bersama gaji masa terakhir.
     *
     * @return array<string, mixed>
     */
    public function reconcile(
        PayrollPeriod $period,
        Employee $employee,
        int $currentGross,
        int $currentJhtJp,
        ?int $excludePayslipId = null,
        ?string $ptkpStatus = null,
    ): array {
        $year = $period->year();

        $prior = Payslip::query()
            ->where('employee_id', $employee->id)
            ->when($excludePayslipId, fn ($q) => $q->whereKeyNot($excludePayslipId))
            ->whereHas('period', fn ($q) => $q->whereYear('start_date', $year)
                ->where('start_date', '<', $period->start_date->toDateString()))
            ->with('period:id,start_date')
            ->get(['id', 'payroll_period_id', 'status', 'gross_earnings', 'employee_jht_jp', 'pph21_amount']);

        $init = EmployeeTaxInitialBalance::query()
            ->where('employee_id', $employee->id)
            ->where('tax_year', $year)
            ->first();

        // Jumlah bulan bekerja untuk plafon biaya jabatan (Rp500.000 per bulan).
        $months = [];
        $warnings = [];
        if ($init) {
            for ($m = $this->firstWorkingMonth($employee, $year); $m <= $init->cutoff_month; $m++) {
                $months[$m] = 'ytd';
            }
        }
        foreach ($prior as $slip) {
            $m = $slip->period->month();
            if (($months[$m] ?? null) === 'ytd') {
                $warnings[] = 'Saldo awal YTD mencakup s/d '.Tanggal::BULAN[$init->cutoff_month].', tetapi ada slip sistem bulan '
                    .Tanggal::BULAN[$m].'. Bruto bulan itu terhitung dua kali — perbaiki saldo awal.';
            }
            $months[$m] = 'system';
        }
        $months[$period->month()] = 'current';
        $monthCount = count($months);

        $initGross = $init?->gross_income_ytd ?? 0;
        $initJhtJp = $init?->employee_jht_jp_ytd ?? 0;
        $initPaid = $init?->pph21_paid_ytd ?? 0;

        $systemGross = (int) $prior->sum('gross_earnings');
        $systemJhtJp = (int) $prior->sum('employee_jht_jp');
        $systemPaid = (int) $prior->sum('pph21_amount');

        $grossYear = $initGross + $systemGross + $currentGross;
        $jhtJpYear = $initJhtJp + $systemJhtJp + $currentJhtJp;
        $paid = $initPaid + $systemPaid;

        $biayaJabatanCap = min(self::BIAYA_JABATAN_MAX_YEARLY, self::BIAYA_JABATAN_MAX_MONTHLY * $monthCount);
        $biayaJabatan = min(Money::pctBp($grossYear, self::BIAYA_JABATAN_BP), $biayaJabatanCap);
        $neto = $grossYear - $biayaJabatan - $jhtJpYear;

        $ptkpStatus = Pph21TerCalculatorService::normalizeStatus($ptkpStatus ?? $this->taxYearPtkpStatus($employee, $year, $period->start_date, $excludePayslipId));
        $ptkp = $this->ter->ptkp($ptkpStatus);
        $pkp = intdiv(max(0, $neto - $ptkp), 1000) * 1000;
        $annualTax = $this->annualTax($pkp);

        return [
            'tax_year' => $year,
            'months_worked' => $monthCount,
            'init_gross' => $initGross,
            'init_jht_jp' => $initJhtJp,
            'init_pph21_paid' => $initPaid,
            'init_cutoff_month' => $init?->cutoff_month,
            'system_gross' => $systemGross,
            'system_jht_jp' => $systemJhtJp,
            'system_pph21_paid' => $systemPaid,
            'system_periods' => $prior->count(),
            'system_draft_periods' => $prior->where('status', Payslip::STATUS_DRAFT)->count(),
            'current_gross' => $currentGross,
            'current_jht_jp' => $currentJhtJp,
            'gross_year' => $grossYear,
            'biaya_jabatan_cap' => $biayaJabatanCap,
            'biaya_jabatan' => $biayaJabatan,
            'jht_jp_year' => $jhtJpYear,
            'neto_year' => $neto,
            'ptkp_status' => $ptkpStatus,
            'ptkp' => $ptkp,
            'pkp' => $pkp,
            'pph21_annual' => $annualTax,
            'pph21_already_paid' => $paid,
            'pph21_last_period' => $annualTax - $paid,
            'warnings' => $warnings,
        ];
    }

    /** Bulan pertama bekerja di tahun pajak (karyawan baru tidak dihitung sejak Januari). */
    public function firstWorkingMonth(Employee $employee, int $year): int
    {
        return ($employee->join_date && (int) $employee->join_date->format('Y') === $year)
            ? (int) $employee->join_date->format('n')
            : 1;
    }

    /** PPh 21 terutang setahun dengan tarif progresif Pasal 17. */
    public function annualTax(int $pkp): int
    {
        $tax = 0;
        $lower = 0;
        foreach (self::PASAL17_LAYERS as [$upper, $bp]) {
            if ($pkp <= $lower) {
                break;
            }
            $slice = ($upper === null ? $pkp : min($pkp, $upper)) - $lower;
            $tax += Money::pctBp($slice, $bp);
            if ($upper === null) {
                break;
            }
            $lower = $upper;
        }

        return $tax;
    }
}
