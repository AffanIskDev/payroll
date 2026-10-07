<?php

namespace Tests\Feature\Payroll;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use App\Services\Payroll\TaxReport1721A1Service;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Modul 5B: Formulir 1721-A1 konsisten dengan rekonsiliasi Desember. */
class TaxReport1721A1Test extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    public function test_baris_22_sama_dengan_pph21_desember_dan_total_dipotong_sama_dengan_pph_setahun(): void
    {
        $employee = Employee::factory()->withProfile([
            'basic_salary' => 7_000_000, 'position_allowance' => 1_000_000, 'monthly_attendance_allowance' => 500_000,
        ])->create(['ptkp_status' => 'K/1']);
        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id, 'tax_year' => 2026, 'cutoff_month' => 9, 'ptkp_status' => 'K/1',
            'gross_income_ytd' => 81_000_000, 'employee_jht_jp_ytd' => 1_890_000, 'pph21_paid_ytd' => 800_000,
        ]);

        $pipeline = app(PayrollPipelineService::class);
        $approval = app(PayslipApprovalService::class);
        $manager = $this->manager();
        foreach ([10, 11, 12] as $month) {
            $period = PayrollPeriod::createForMonth(2026, $month);
            $pipeline->generateMonthlyBatch($period);
            $approval->lockAll($period, $manager);
        }

        $december = Payslip::whereHas('period', fn ($q) => $q->where('period_code', '2026-12'))->firstOrFail();
        $this->assertSame('PASAL17', $december->pph21_method);

        $report = app(TaxReport1721A1Service::class)->generateAnnualReport($employee, 2026);
        $l = $report['lines'];

        $this->assertTrue($report['is_final']);
        $this->assertSame([], $report['warnings']);
        $this->assertSame(81_000_000 + (int) Payslip::sum('gross_earnings'), $l[8]);
        $this->assertSame($l[1] + $l[3] + $l[5] + $l[7], $l[8]);
        $this->assertSame($december->pph21_amount, $l[22]);
        $this->assertSame($l[18], $l[21] + $l[22]);
        $this->assertSame($l[18], 800_000 + (int) Payslip::sum('pph21_amount'), 'Total dipotong setahun = PPh terutang setahun');
        $this->assertSame(12, $report['months_worked']);

        $this->actingAs($manager)->get("/hr-manager/tax/1721-a1/2026/{$employee->id}")
            ->assertOk()->assertHeader('Content-Type', 'application/pdf');
        $this->get('/hr-manager/tax/1721-a1/2026')->assertOk()->assertSee('Final');
        $zip = $this->get('/hr-manager/tax/1721-a1/2026/zip')->assertOk();
        $this->assertSame('application/zip', $zip->headers->get('Content-Type'));

        // Karyawan bisa mengunduh 1721-A1 final (terenkripsi) lewat API Rumatku.
        Sanctum::actingAs(User::factory()->forEmployee($employee)->create());
        $api = $this->get('/api/v1/employee/tax-documents/2026')->assertOk();
        $api->assertHeader('Content-Type', 'application/pdf');
        $this->assertStringContainsString('/Encrypt', $api->getContent());
    }

    public function test_tahun_tanpa_masa_terakhir_ditandai_sementara(): void
    {
        $budi = $this->createBudi();
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);
        app(PayslipApprovalService::class)->lockAll($period, $this->manager());

        $report = app(TaxReport1721A1Service::class)->generateAnnualReport($budi, 2026);

        $this->assertFalse($report['is_final']);
        $this->assertNotEmpty($report['warnings']);
    }
}
