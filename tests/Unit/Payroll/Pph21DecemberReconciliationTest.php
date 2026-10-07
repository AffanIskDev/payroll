<?php

namespace Tests\Unit\Payroll;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Services\Payroll\Pph21CalculatorService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Modul 4B: karyawan K/1 yang masuk sistem baru sejak Oktober, dengan saldo
 * awal YTD impor Januari–September.
 */
class Pph21DecemberReconciliationTest extends TestCase
{
    use RefreshDatabase;

    private function slip(Employee $employee, PayrollPeriod $period, int $gross, int $jhtJp, int $pph21): void
    {
        Payslip::create([
            'payroll_period_id' => $period->id,
            'employee_id' => $employee->id,
            'status' => Payslip::STATUS_PUBLISHED,
            'employee_nik' => $employee->nik,
            'employee_name' => $employee->full_name,
            'ptkp_status' => $employee->ptkp_status,
            'basic_salary' => $gross,
            'gross_earnings' => $gross,
            'employee_jht_jp' => $jhtJp,
            'pph21_amount' => $pph21,
            'terbilang' => '-',
            'bank_name' => 'BCA',
            'bank_account_number' => '123',
        ]);
    }

    public function test_pph21_desember_sama_dengan_pajak_setahun_dikurangi_potongan_jan_nov(): void
    {
        $employee = Employee::factory()->create(['ptkp_status' => 'K/1']);

        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id,
            'tax_year' => 2026,
            'cutoff_month' => 9,
            'ptkp_status' => 'K/1',
            'gross_income_ytd' => 81_000_000,
            'employee_jht_jp_ytd' => 1_620_000,
            'biaya_jabatan_ytd' => 4_050_000,
            'pph21_paid_ytd' => 900_000,
        ]);

        // Oktober & November di sistem baru: bruto 9 jt, TER B 1% = 90.000.
        $this->slip($employee, PayrollPeriod::createForMonth(2026, 10), 9_000_000, 180_000, 90_000);
        $this->slip($employee, PayrollPeriod::createForMonth(2026, 11), 9_000_000, 180_000, 90_000);
        $december = PayrollPeriod::createForMonth(2026, 12);

        $result = app(Pph21CalculatorService::class)
            ->calculateTaxForPeriod($december, $employee, 9_000_000, 180_000);

        // Hitung manual (Pasal 17 UU HPP):
        $brutoSetahun = 81_000_000 + 9_000_000 * 3;                      // 108.000.000
        $biayaJabatan = min((int) round($brutoSetahun * 0.05), 6_000_000); // 5.400.000
        $iuranSetahun = 1_620_000 + 180_000 * 3;                         // 2.160.000
        $neto = $brutoSetahun - $biayaJabatan - $iuranSetahun;           // 100.440.000
        $pkp = intdiv($neto - 63_000_000, 1000) * 1000;                  // 37.440.000
        $pajakSetahun = (int) round($pkp * 0.05);                        // 1.872.000
        $sudahDipotong = 900_000 + 90_000 + 90_000;                      // 1.080.000

        $this->assertSame('PASAL17', $result['method']);
        $this->assertSame($brutoSetahun, $result['breakdown']['gross_year']);
        $this->assertSame($biayaJabatan, $result['breakdown']['biaya_jabatan']);
        $this->assertSame($pkp, $result['breakdown']['pkp']);
        $this->assertSame($pajakSetahun, $result['breakdown']['pph21_annual']);
        $this->assertSame($pajakSetahun - $sudahDipotong, $result['amount']);
        $this->assertSame(792_000, $result['amount']);
        $this->assertSame(12, $result['breakdown']['months_worked']);
        $this->assertSame([], $result['breakdown']['warnings']);
    }

    public function test_bulan_januari_sampai_november_tetap_memakai_ter(): void
    {
        $employee = Employee::factory()->create(['ptkp_status' => 'K/1']);

        $result = app(Pph21CalculatorService::class)
            ->calculateTaxForPeriod(PayrollPeriod::createForMonth(2026, 11), $employee, 9_914_400, 180_000);

        $this->assertSame('TER', $result['method']);
        $this->assertSame(148_716, $result['amount']);
    }

    public function test_lebih_potong_menghasilkan_nilai_negatif_untuk_dikembalikan(): void
    {
        $employee = Employee::factory()->create(['ptkp_status' => 'K/3']);
        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id, 'tax_year' => 2026, 'cutoff_month' => 11, 'ptkp_status' => 'K/3',
            'gross_income_ytd' => 77_000_000, 'employee_jht_jp_ytd' => 1_890_000, 'pph21_paid_ytd' => 2_000_000,
        ]);

        $result = app(Pph21CalculatorService::class)
            ->calculateTaxForPeriod(PayrollPeriod::createForMonth(2026, 12), $employee, 7_000_000, 210_000);

        // Neto 84 jt − 4,2 jt − 2,1 jt = 77,7 jt; PKP 5,7 jt; pajak 285.000; sudah 2 jt → kembali 1.715.000.
        $this->assertSame(285_000, $result['breakdown']['pph21_annual']);
        $this->assertSame(-1_715_000, $result['amount']);
    }

    public function test_karyawan_resign_direkonsiliasi_di_bulan_resign_dengan_plafon_biaya_jabatan_proporsional(): void
    {
        $employee = Employee::factory()->create(['ptkp_status' => 'TK/0', 'resign_date' => '2026-06-20']);
        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id, 'tax_year' => 2026, 'cutoff_month' => 5, 'ptkp_status' => 'TK/0',
            'gross_income_ytd' => 150_000_000, 'pph21_paid_ytd' => 10_000_000,
        ]);

        $result = app(Pph21CalculatorService::class)
            ->calculateTaxForPeriod(PayrollPeriod::createForMonth(2026, 6), $employee, 30_000_000, 0);

        $this->assertSame('PASAL17', $result['method']);
        $this->assertSame(6, $result['breakdown']['months_worked']);
        $this->assertSame(3_000_000, $result['breakdown']['biaya_jabatan']); // 6 × 500.000, bukan 6 jt
    }

    public function test_tarif_progresif_pasal_17(): void
    {
        $service = app(Pph21CalculatorService::class);

        $this->assertSame(3_000_000, $service->annualTax(60_000_000));
        $this->assertSame(9_000_000, $service->annualTax(100_000_000));          // 3 jt + 15% × 40 jt
        $this->assertSame(31_500_000, $service->annualTax(250_000_000));         // 3 jt + 15% × 190 jt
        $this->assertSame(94_000_000, $service->annualTax(500_000_000));         // 3 + 28,5 + 62,5 jt
        $this->assertSame(1_444_000_000 + 35_000_000, $service->annualTax(5_100_000_000));
    }

    public function test_peringatan_saat_saldo_awal_tumpang_tindih_dengan_slip_sistem(): void
    {
        $employee = Employee::factory()->create(['ptkp_status' => 'TK/0']);
        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id, 'tax_year' => 2026, 'cutoff_month' => 10, 'ptkp_status' => 'TK/0',
            'gross_income_ytd' => 60_000_000,
        ]);
        $this->slip($employee, PayrollPeriod::createForMonth(2026, 10), 6_000_000, 0, 0);

        $result = app(Pph21CalculatorService::class)
            ->calculateTaxForPeriod(PayrollPeriod::createForMonth(2026, 12), $employee, 6_000_000, 0);

        $this->assertNotEmpty($result['breakdown']['warnings']);
    }
}
