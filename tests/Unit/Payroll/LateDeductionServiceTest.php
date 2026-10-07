<?php

namespace Tests\Unit\Payroll;

use App\Models\AttendanceLog;
use App\Models\Employee;
use App\Services\Payroll\LateDeductionService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Tests\TestCase;

class LateDeductionServiceTest extends TestCase
{
    use RefreshDatabase;

    private function service(): LateDeductionService
    {
        return app(LateDeductionService::class);
    }

    /** Kriteria keberterimaan 2: 65 menit di satu hari → max(Rule A=1, Rule C=1) = 1 hari, bukan 2. */
    public function test_denda_tidak_dobel_saat_rule_a_dan_c_sama_sama_berlaku(): void
    {
        $result = $this->service()->evaluate([65], 1_000_000);

        $this->assertSame(1, $result['rule_a_days']);
        $this->assertSame(1, $result['rule_c_days']);
        $this->assertSame(1, $result['penalty_days']);
        $this->assertSame(40_000, $result['deduction_amount']); // 1/25 × 1.000.000
        $this->assertSame('Rule A & C', $result['rule_applied']);
    }

    public function test_rule_b_setiap_tiga_kali_terlambat_15_menit(): void
    {
        // 6 × 16 menit = 96 menit → A=0, B=floor(6/3)=2, C=floor(96/60)=1
        $result = $this->service()->evaluate([16, 16, 16, 16, 16, 16], 1_000_000);

        $this->assertSame(0, $result['rule_a_days']);
        $this->assertSame(2, $result['rule_b_days']);
        $this->assertSame(1, $result['rule_c_days']);
        $this->assertSame(2, $result['penalty_days']);
        $this->assertSame(80_000, $result['deduction_amount']);
        $this->assertSame('Rule B', $result['rule_applied']);
    }

    public function test_rule_c_akumulasi_menit_kecil_kecil(): void
    {
        // 14 menit × 10 hari = 140 menit: tidak ada yang >= 15 → B=0; C=2
        $result = $this->service()->evaluate(array_fill(0, 10, 14), 1_000_000);

        $this->assertSame(0, $result['rule_b_days']);
        $this->assertSame(2, $result['rule_c_days']);
        $this->assertSame(2, $result['penalty_days']);
    }

    public function test_contoh_slip_dua_hari_penalti(): void
    {
        $result = $this->service()->evaluate([62, 63, 0, 0], 1_000_000);

        $this->assertSame(2, $result['penalty_days']);
        $this->assertSame(80_000, $result['deduction_amount']);
    }

    public function test_potongan_dibatasi_maksimal_tunjangan_kehadiran(): void
    {
        $result = $this->service()->evaluate(array_fill(0, 26, 120), 1_000_000);

        $this->assertSame(52, $result['penalty_days']);
        $this->assertSame(1_000_000, $result['deduction_amount']);
    }

    public function test_tanpa_keterlambatan_tanpa_potongan(): void
    {
        $result = $this->service()->evaluate([0, 0, 5], 1_000_000);

        $this->assertSame(0, $result['penalty_days']);
        $this->assertSame(0, $result['deduction_amount']);
        $this->assertNull($result['rule_applied']);
    }

    public function test_calculate_penalty_membaca_log_presensi_periode(): void
    {
        $employee = Employee::factory()->create();
        foreach ([['2026-03-02', 65, 'HADIR'], ['2026-03-03', 0, 'HADIR'], ['2026-04-01', 90, 'HADIR'], ['2026-03-04', 0, 'SAKIT']] as [$date, $late, $status]) {
            AttendanceLog::create(['employee_id' => $employee->id, 'work_date' => $date, 'status' => $status, 'late_minutes' => $late]);
        }

        $result = $this->service()->calculatePenalty(
            $employee->id,
            Carbon::parse('2026-03-01'),
            Carbon::parse('2026-03-31'),
            1_000_000,
        );

        $this->assertSame(1, $result['penalty_days']);   // log April tidak ikut
        $this->assertSame(40_000, $result['deduction_amount']);
    }
}
