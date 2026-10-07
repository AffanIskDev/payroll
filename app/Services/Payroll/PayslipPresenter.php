<?php

namespace App\Services\Payroll;

use App\Models\Payslip;
use App\Support\BankDirectory;
use App\Support\Money;
use App\Support\Tanggal;

/**
 * Menyusun teks tampilan slip (label, keterangan rumus, nominal) satu kali
 * untuk dipakai bersama oleh PDF, workbench Manager HRD, dan menu ESS.
 */
class PayslipPresenter
{
    public function __construct(private readonly PayrollSettings $settings) {}

    /** @return array<string, mixed> */
    public function present(Payslip $slip): array
    {
        $slip->loadMissing('period');
        $period = $slip->period;
        $system = $slip->system_values ?? [];
        $overrides = $slip->overrides ?? [];
        $bpjs = $slip->bpjs_breakdown ?? [];
        $workDays = (int) (($system['late']['work_days_basis'] ?? null) ?: $this->settings->int('DEFAULT_WORK_DAYS'));

        return [
            'company_name' => $this->settings->get('COMPANY_NAME'),
            'period_label' => 'Periode: '.$period->period_name.' ('.$period->cutoffLabel().')',
            'meta_left' => [
                ['Nama Karyawan', $slip->employee_name],
                ['NIK / Employee ID', $slip->employee_nik],
                ['Jabatan & Divisi', trim($slip->position.' • '.$slip->department, ' •')],
                ['Status Hubungan Kerja', $slip->employment_status ?: '-'],
            ],
            'meta_right' => [
                ['Status PTKP & Pajak', $this->taxStatusLabel($slip)],
                ['Dasar Upah Pokok', Money::rupiah($slip->basic_salary)],
                ['Basis Floor BPJS Kes', $this->kesBaseLabel($slip, $bpjs)],
                ['Standar Hari Kerja', $workDays.' Hari (PP 35/2021)'],
            ],
            'stats' => [
                ['HARI HADIR', $slip->attended_days.' Hari'],
                ['IZIN / SAKIT', $slip->leave_sick_days.' Hari'],
                ['JAM LEMBUR', $this->hours($slip->overtime_hours).' Jam'],
                ['PENALTI TERLAMBAT', $slip->late_penalty_days.' Hari Potong'],
            ],
            'earnings' => $this->earnings($slip, $system, $overrides, $bpjs, $workDays),
            'deductions' => $this->deductions($slip, $overrides, $bpjs, $workDays),
            'gross' => $slip->gross_earnings,
            'total_deductions' => $slip->total_deductions,
            'thp' => $slip->take_home_pay,
            'terbilang' => $slip->terbilang,
            'bank_label' => BankDirectory::label($slip->bank_name).' • '.$slip->bank_account_number,
            'account_name' => mb_strtoupper((string) $slip->bank_account_name),
            'payment_date' => Tanggal::panjang($period->payment_date),
            'employee_name' => $slip->employee_name,
            'signer_name' => $this->settings->get('HR_MANAGER_NAME'),
            'signer_title' => $this->settings->get('HR_MANAGER_TITLE'),
            'pph21_method' => $slip->pph21_method,
            'pph21_breakdown' => $slip->pph21_breakdown ?? [],
        ];
    }

    public function taxStatusLabel(Payslip $slip): string
    {
        if ($slip->pph21_method === 'PASAL17') {
            return $slip->ptkp_status.' • Pasal 17 (Masa Terakhir)';
        }

        return $slip->ptkp_status.' • TER '.$slip->ter_category.' ('.Money::bpToPercent((int) round(($slip->ter_rate ?? 0) * 100), true).')';
    }

    /** @param array<string, mixed> $bpjs */
    private function kesBaseLabel(Payslip $slip, array $bpjs): string
    {
        $umk = (int) ($bpjs['umk'] ?? $this->settings->money('UMK_BEKASI_REGENCY'));
        $base = $slip->bpjs_kes_base_salary;

        if (! empty($bpjs['kes_cap_applied'])) {
            return Money::rupiah($base).' (Plafon maks.)';
        }
        if (! empty($bpjs['umk_floor_applied'])) {
            return Money::rupiah($base).' (Floor UMK, pokok < UMK)';
        }

        return Money::rupiah($base).' (> UMK '.Money::rupiah($umk).')';
    }

    /**
     * @param  array<string, mixed>  $system
     * @param  array<string, mixed>  $overrides
     * @param  array<string, mixed>  $bpjs
     * @return list<array{key: string, label: string, caption: string, amount: int, editable: bool}>
     */
    private function earnings(Payslip $slip, array $system, array $overrides, array $bpjs, int $workDays): array
    {
        $systemOvertime = $this->hours((float) ($system['overtime_hours'] ?? $slip->overtime_hours))
            .' Jam × '.Money::rupiah($slip->overtime_rate).' (Flat Rate)';
        $kpiScore = $slip->kpi_score !== null ? 'Hasil Skor Rosy: '.$this->hours($slip->kpi_score).' Poin' : 'Tidak ada skor KPI periode ini';

        return [
            $this->row('basic_salary', 'Gaji Pokok', 'Fixed Master ROSY', $slip->basic_salary),
            $this->row('position_allowance', 'Tunjangan Jabatan', 'Tunjangan Tetap', $slip->position_allowance),
            $this->row('attendance_allowance', 'Tunjangan Kehadiran', 'Standar Penuh '.$workDays.' Hari', $slip->attendance_allowance),
            $this->row('tunjangan_bpjs_kes', 'Tunjangan BPJS Kesehatan', $this->kesAllowanceCaption($bpjs), $slip->tunjangan_bpjs_kes),
            $this->row('tunjangan_bpjs_tk', 'Tunjangan BPJS Ketenagakerjaan', $this->tkAllowanceCaption($bpjs), $slip->tunjangan_bpjs_tk),
            $this->row('overtime_pay', 'Upah Lembur (Overtime)',
                isset($overrides['overtime_pay']) ? 'Disesuaikan Manager HRD (sistem: '.$systemOvertime.')' : $systemOvertime,
                $slip->overtime_pay, true),
            $this->row('kpi_incentive', 'Insentif KPI / Kinerja',
                isset($overrides['kpi_incentive']) ? 'Disesuaikan Manager HRD ('.$kpiScore.')' : $kpiScore,
                $slip->kpi_incentive, true),
            $this->row('additional_bonus', 'Bonus Tambahan',
                $slip->additional_bonus > 0 ? 'Disetujui Manager HRD' : 'Tidak ada bonus periode ini',
                $slip->additional_bonus, true),
        ];
    }

    /**
     * @param  array<string, mixed>  $overrides
     * @param  array<string, mixed>  $bpjs
     * @return list<array{key: string, label: string, caption: string, amount: int, editable: bool}>
     */
    private function deductions(Payslip $slip, array $overrides, array $bpjs, int $workDays): array
    {
        $formula = '('.$slip->late_penalty_days.'/'.$workDays.') × Tunj. Kehadiran';
        $lateCaption = match (true) {
            isset($overrides['late_penalty_amount']) => 'Disesuaikan Manager HRD (sistem: '.$formula.')',
            $slip->late_penalty_days > 0 => 'Rumus '.$formula,
            default => 'Tidak ada penalti (Rule A/B/C)',
        };

        if ($slip->pph21_method === 'PASAL17') {
            $taxLabel = $slip->pph21_amount < 0 ? 'Pengembalian Lebih Potong PPh 21' : 'Pajak Penghasilan (PPh 21 Masa Terakhir)';
            $taxCaption = 'Rekonsiliasi Pasal 17 UU HPP (PPh setahun − dipotong Jan–Nov)';
        } else {
            $taxLabel = 'Pajak Penghasilan (PPh 21 TER)';
            $taxCaption = 'TER Kategori '.$slip->ter_category.': '
                .Money::bpToPercent((int) round(($slip->ter_rate ?? 0) * 100), true).' × Bruto Pajak';
        }

        $otherCaption = isset($overrides['other_deductions'])
            ? 'Disesuaikan Manager HRD'
            : ($slip->other_deductions_note ?: 'Tidak ada kasbon periode ini');

        return [
            $this->row('late_penalty_amount', 'Potongan Keterlambatan', $lateCaption, $slip->late_penalty_amount, true),
            $this->row('iuran_bpjs_kes_total', 'Iuran BPJS Kesehatan Total',
                ($bpjs['has_bpjs_kes'] ?? true) ? 'Total Setor 5% (4% Persh + 1% Karyawan)' : 'Tidak ikut program',
                $slip->iuran_bpjs_kes_total),
            $this->row('iuran_bpjs_tk_total', 'Iuran BPJS Ketenagakerjaan Total', $this->tkRemittanceCaption($bpjs), $slip->iuran_bpjs_tk_total),
            $this->row('pph21_amount', $taxLabel, $taxCaption, $slip->pph21_amount),
            $this->row('other_deductions', 'Potongan Kasbon / Lainnya', $otherCaption, $slip->other_deductions, true),
        ];
    }

    /** @param array<string, mixed> $bpjs */
    private function kesAllowanceCaption(array $bpjs): string
    {
        return match (true) {
            ! ($bpjs['has_bpjs_kes'] ?? true) => 'Tidak ikut program',
            ! empty($bpjs['kes_cap_applied']) => 'Porsi Perusahaan 4% × Plafon Upah',
            ! empty($bpjs['umk_floor_applied']) => 'Porsi Perusahaan 4% × UMK Kab. Bekasi',
            default => 'Porsi Perusahaan 4% × Upah Pokok',
        };
    }

    /** @param array<string, mixed> $bpjs */
    private function tkAllowanceCaption(array $bpjs): string
    {
        $parts = [];
        if ($bpjs['has_jkk'] ?? true) {
            $parts[] = 'JKK ('.Money::bpToPercent((int) ($bpjs['jkk_rate_bp'] ?? 24)).')';
        }
        if ($bpjs['has_jkm'] ?? true) {
            $parts[] = 'JKM ('.Money::bpToPercent(BpjsCalculatorService::JKM_BP).')';
        }
        if ($bpjs['has_jht'] ?? true) {
            $parts[] = 'JHT ('.Money::bpToPercent(BpjsCalculatorService::JHT_COMPANY_BP).')';
        }
        if ($bpjs['has_jp'] ?? true) {
            $parts[] = 'JP ('.Money::bpToPercent(BpjsCalculatorService::JP_COMPANY_BP).')'
                .(! empty($bpjs['jp_cap_applied']) ? ' maks. plafon' : '');
        }

        return $parts ? implode(', ', $parts) : 'Tidak ikut program';
    }

    /** @param array<string, mixed> $bpjs */
    private function tkRemittanceCaption(array $bpjs): string
    {
        $parts = [];
        if ($bpjs['has_jht'] ?? true) {
            $parts[] = 'JHT ('.Money::bpToPercent(BpjsCalculatorService::JHT_COMPANY_BP + BpjsCalculatorService::JHT_EMPLOYEE_BP).')';
        }
        if ($bpjs['has_jp'] ?? true) {
            $parts[] = 'JP ('.Money::bpToPercent(BpjsCalculatorService::JP_COMPANY_BP + BpjsCalculatorService::JP_EMPLOYEE_BP).')';
        }
        if ($bpjs['has_jkk'] ?? true) {
            $parts[] = 'JKK';
        }
        if ($bpjs['has_jkm'] ?? true) {
            $parts[] = 'JKM';
        }

        return $parts ? 'Total Setor '.implode(', ', $parts) : 'Tidak ikut program';
    }

    /** @return array{key: string, label: string, caption: string, amount: int, editable: bool} */
    private function row(string $key, string $label, string $caption, int $amount, bool $editable = false): array
    {
        return compact('key', 'label', 'caption', 'amount', 'editable');
    }

    /** 7.0 → "7", 7.5 → "7,5" */
    private function hours(float|int|null $value): string
    {
        $value = (float) $value;

        return floor($value) == $value
            ? number_format($value, 0, ',', '.')
            : rtrim(rtrim(number_format($value, 2, ',', '.'), '0'), ',');
    }
}
