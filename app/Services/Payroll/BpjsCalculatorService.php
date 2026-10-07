<?php

namespace App\Services\Payroll;

use App\Models\EmployeeSalaryProfile;
use App\Support\Money;

/**
 * BPJS metode Full Gross (PRD 3.4, Modul 1B): basis murni Gaji Pokok, floor UMK
 * Kab. Bekasi + plafon untuk BPJS Kesehatan, plafon untuk JP. Porsi perusahaan
 * dibayar sebagai tunjangan (penerimaan), lalu seluruh iuran (perusahaan +
 * pekerja) dipotong sebagai setoran total.
 */
class BpjsCalculatorService
{
    // Tarif statutori dalam basis poin (1 bp = 0,01%).
    public const KES_COMPANY_BP = 400;   // 4%

    public const KES_EMPLOYEE_BP = 100;  // 1%

    public const JKM_BP = 30;            // 0,30%

    public const JHT_COMPANY_BP = 370;   // 3,70%

    public const JHT_EMPLOYEE_BP = 200;  // 2%

    public const JP_COMPANY_BP = 200;    // 2%

    public const JP_EMPLOYEE_BP = 100;   // 1%

    public function __construct(private readonly PayrollSettings $settings) {}

    /**
     * @return array<string, int|float|bool>
     */
    public function calculate(float|int $basicSalary, EmployeeSalaryProfile $profile): array
    {
        $basic = Money::round($basicSalary);
        $umk = $this->settings->money('UMK_BEKASI_REGENCY');
        $kesCap = $this->settings->money('BPJS_KES_MAX_WAGE');
        $jpCap = $this->settings->money('BPJS_JP_MAX_WAGE');

        $kesBase = min(max($basic, $umk), $kesCap);
        $tkBase = $basic;
        $jpBase = min($basic, $jpCap);
        $jkkBp = Money::rateToBp($profile->jkk_rate);

        $kesCompany = $profile->has_bpjs_kes ? Money::pctBp($kesBase, self::KES_COMPANY_BP) : 0;
        $kesEmployee = $profile->has_bpjs_kes ? Money::pctBp($kesBase, self::KES_EMPLOYEE_BP) : 0;
        $jkk = $profile->has_jkk ? Money::pctBp($tkBase, $jkkBp) : 0;
        $jkm = $profile->has_jkm ? Money::pctBp($tkBase, self::JKM_BP) : 0;
        $jhtCompany = $profile->has_jht ? Money::pctBp($tkBase, self::JHT_COMPANY_BP) : 0;
        $jhtEmployee = $profile->has_jht ? Money::pctBp($tkBase, self::JHT_EMPLOYEE_BP) : 0;
        $jpCompany = $profile->has_jp ? Money::pctBp($jpBase, self::JP_COMPANY_BP) : 0;
        $jpEmployee = $profile->has_jp ? Money::pctBp($jpBase, self::JP_EMPLOYEE_BP) : 0;

        return [
            'kes_base' => $kesBase,
            'tk_base' => $tkBase,
            'jp_base' => $jpBase,
            'umk' => $umk,
            'umk_floor_applied' => $basic < $umk,
            'kes_cap_applied' => max($basic, $umk) > $kesCap,
            'jp_cap_applied' => $basic > $jpCap,
            'jkk_rate_bp' => $jkkBp,

            'kes_company' => $kesCompany,
            'kes_employee' => $kesEmployee,
            'jkk' => $jkk,
            'jkm' => $jkm,
            'jht_company' => $jhtCompany,
            'jht_employee' => $jhtEmployee,
            'jp_company' => $jpCompany,
            'jp_employee' => $jpEmployee,

            // Penerimaan (tunjangan dari perusahaan)
            'tunjangan_bpjs_kes' => $kesCompany,
            'tunjangan_bpjs_tk' => $jkk + $jkm + $jhtCompany + $jpCompany,

            // Potongan (setoran total ke BPJS)
            'iuran_bpjs_kes_total' => $kesCompany + $kesEmployee,
            'iuran_bpjs_tk_total' => $jkk + $jkm + $jhtCompany + $jhtEmployee + $jpCompany + $jpEmployee,

            // Porsi pekerja JHT + JP, pengurang penghasilan neto tahunan
            'employee_jht_jp' => $jhtEmployee + $jpEmployee,
        ];
    }
}
