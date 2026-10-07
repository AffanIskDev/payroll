<?php

namespace Tests\Feature;

use App\Models\Employee;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Kriteria keberterimaan 4: menu & endpoint edit slip hanya untuk MANAGER_HRD. */
class AccessControlTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    public static function nonManagerRoles(): array
    {
        return [[User::ROLE_STAFF_HRD], [User::ROLE_ATASAN_DIVISI], [User::ROLE_KARYAWAN]];
    }

    #[DataProvider('nonManagerRoles')]
    public function test_selain_manager_hrd_ditolak_dari_modul_payroll(string $role): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);

        $user = User::factory()->role($role)->create();
        $this->actingAs($user);

        $this->get('/hr-manager/payroll')->assertForbidden();
        $this->get("/hr-manager/payroll/{$period->id}")->assertForbidden();
        $this->get("/hr-manager/payroll/{$period->id}/employee/{$budi->id}")->assertForbidden();
        $this->post("/hr-manager/payroll/{$period->id}/approve-all")->assertForbidden();
        $this->post("/hr-manager/payroll/{$period->id}/export-bsi", ['debit_account' => '7001234567', 'effective_date' => '2026-04-01'])->assertForbidden();
        $this->get('/hr-manager/payroll/import-ytd')->assertForbidden();
        $this->get('/hr-manager/tax/1721-a1/2026')->assertForbidden();
        $this->assertSame(Payslip::STATUS_DRAFT, Payslip::first()->status);
    }

    public function test_tamu_diarahkan_ke_login(): void
    {
        $this->get('/hr-manager/payroll')->assertRedirect('/login');
        $this->get('/my/payslips')->assertRedirect('/login');
    }

    public function test_staff_hrd_tidak_melihat_gaji_manajemen(): void
    {
        $budi = $this->createBudi();
        $boss = Employee::factory()->withProfile(['basic_salary' => 30_000_000])->create(['full_name' => 'Direktur Rahasia', 'is_management' => true]);
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);

        $this->actingAs(User::factory()->role(User::ROLE_STAFF_HRD)->create())
            ->get("/hr-staff/attendance/{$period->id}")
            ->assertOk()
            ->assertSee('Budi Santoso')
            ->assertDontSee('Direktur Rahasia');

        $this->actingAs(User::factory()->managerHrd()->create())
            ->get("/hr-staff/attendance/{$period->id}")
            ->assertOk()
            ->assertSee('Direktur Rahasia');
    }

    public function test_karyawan_hanya_bisa_unduh_slip_sendiri_lewat_web(): void
    {
        $budi = $this->createBudi();
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);
        app(PayslipApprovalService::class)->lockAll($period, $this->manager());
        $slip = Payslip::firstOrFail();

        $other = User::factory()->forEmployee(Employee::factory()->create())->create();
        $this->actingAs($other)->get("/my/payslips/{$slip->id}/download")->assertForbidden();

        $owner = User::factory()->forEmployee($budi)->create();
        $this->actingAs($owner)->get("/my/payslips/{$slip->id}/download")->assertOk()->assertHeader('Content-Type', 'application/pdf');
    }
}
