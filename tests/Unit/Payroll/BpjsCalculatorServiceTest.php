<?php

namespace Tests\Unit\Payroll;

use App\Models\EmployeeSalaryProfile;
use App\Models\PayrollConfig;
use App\Services\Payroll\BpjsCalculatorService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class BpjsCalculatorServiceTest extends TestCase
{
    use RefreshDatabase;

    private const UMK = 5_938_885;

    private function profile(array $attributes = []): EmployeeSalaryProfile
    {
        return new EmployeeSalaryProfile($attributes + [
            'has_bpjs_kes' => true, 'has_jkk' => true, 'has_jkm' => true, 'has_jht' => true, 'has_jp' => true,
            'jkk_rate' => 0.0024,
        ]);
    }

    private function calc(int $basic, array $profile = []): array
    {
        return app(BpjsCalculatorService::class)->calculate($basic, $this->profile($profile));
    }

    public function test_angka_contoh_slip_gaji_pokok_6_juta(): void
    {
        $r = $this->calc(6_000_000);

        $this->assertSame(240_000, $r['tunjangan_bpjs_kes']);   // 4%
        $this->assertSame(374_400, $r['tunjangan_bpjs_tk']);    // JKK 0,24 + JKM 0,3 + JHT 3,7 + JP 2
        $this->assertSame(300_000, $r['iuran_bpjs_kes_total']); // 5%
        $this->assertSame(554_400, $r['iuran_bpjs_tk_total']);  // JKK + JKM + JHT 5,7 + JP 3
        $this->assertSame(180_000, $r['employee_jht_jp']);      // JHT 2% + JP 1%
        $this->assertFalse($r['umk_floor_applied']);
    }

    /** Kriteria keberterimaan 1: pokok Rp 4.500.000 < UMK → basis BPJS Kes naik ke UMK. */
    public function test_floor_umk_bekasi_untuk_bpjs_kesehatan(): void
    {
        $r = $this->calc(4_500_000);

        $this->assertSame(self::UMK, $r['kes_base']);
        $this->assertTrue($r['umk_floor_applied']);
        $this->assertSame((int) round(self::UMK * 0.04), $r['tunjangan_bpjs_kes']); // 237.555
        $this->assertSame((int) round(self::UMK * 0.04) + (int) round(self::UMK * 0.01), $r['iuran_bpjs_kes_total']);
        $this->assertSame(296_944, $r['iuran_bpjs_kes_total']);
        // Basis BPJS Ketenagakerjaan tetap gaji pokok murni.
        $this->assertSame(4_500_000, $r['tk_base']);
        $this->assertSame(280_800, $r['tunjangan_bpjs_tk']);
    }

    public function test_plafon_bpjs_kesehatan_dan_jaminan_pensiun(): void
    {
        $r = $this->calc(22_000_000);

        $this->assertSame(12_000_000, $r['kes_base']);
        $this->assertSame(480_000, $r['tunjangan_bpjs_kes']);
        $this->assertSame(10_547_400, $r['jp_base']);
        $this->assertSame(210_948, $r['jp_company']);
        $this->assertSame(105_474, $r['jp_employee']);
        $this->assertTrue($r['kes_cap_applied']);
        $this->assertTrue($r['jp_cap_applied']);
    }

    public function test_umk_mengikuti_nilai_di_pengaturan(): void
    {
        PayrollConfig::create(['config_key' => 'UMK_BEKASI_REGENCY', 'config_value' => '5219263']);

        $this->assertSame(5_219_263, $this->calc(4_500_000)['kes_base']);
    }

    public function test_checklist_program_dan_tarif_jkk(): void
    {
        $r = $this->calc(6_000_000, ['has_jp' => false, 'has_bpjs_kes' => false, 'jkk_rate' => 0.0054]);

        $this->assertSame(0, $r['tunjangan_bpjs_kes']);
        $this->assertSame(0, $r['iuran_bpjs_kes_total']);
        $this->assertSame(0, $r['jp_company']);
        $this->assertSame(32_400, $r['jkk']);   // 0,54%
        $this->assertSame(32_400 + 18_000 + 222_000, $r['tunjangan_bpjs_tk']);
        $this->assertSame(120_000, $r['employee_jht_jp']); // hanya JHT 2%
    }
}
