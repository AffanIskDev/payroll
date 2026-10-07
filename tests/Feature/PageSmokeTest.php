<?php

namespace Tests\Feature;

use App\Models\Employee;
use App\Models\KpiScore;
use App\Models\PayrollConfig;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Semua halaman utama tampil tanpa error untuk peran masing-masing. */
class PageSmokeTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    public function test_halaman_login_dan_alur_masuk_sesuai_peran(): void
    {
        $this->get('/login')->assertOk()->assertSee('Masuk');

        $manager = User::factory()->managerHrd()->create(['email' => 'm@rosy.test']);
        $this->post('/login', ['email' => 'm@rosy.test', 'password' => 'password'])->assertRedirect('/hr-manager/payroll');
        $this->post('/logout')->assertRedirect('/login');

        $this->post('/login', ['email' => 'm@rosy.test', 'password' => 'salah'])->assertSessionHasErrors('email');
    }

    public function test_halaman_manager_hrd(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);
        $manager = $this->manager();
        $this->actingAs($manager);

        $this->get('/dashboard')->assertRedirect('/hr-manager/payroll');
        $this->get('/hr-manager/payroll')->assertOk()->assertSee('Maret 2026');
        $this->get("/hr-manager/payroll/{$period->id}")->assertOk()->assertSee('Budi Santoso')->assertSee('Approve &amp; Lock Semua', false);
        $this->get("/hr-manager/payroll/{$period->id}?status=draft&q=budi")->assertOk()->assertSee('Budi Santoso');
        $this->get("/hr-manager/payroll/{$period->id}/employee/{$budi->id}/preview-pdf")->assertOk()->assertHeader('Content-Type', 'application/pdf');
        $this->get("/hr-manager/payroll/{$period->id}/employee/{$budi->id}/pdf")->assertNotFound();
        $this->get('/hr-manager/employees')->assertOk()->assertSee('8820192831');
        $this->get("/hr-manager/employees/{$budi->id}/salary-profile")->assertOk();
        $this->get('/hr-manager/payroll/settings')->assertOk()->assertSee('UMK Kabupaten Bekasi');
        $this->get('/hr-manager/payroll/import-ytd')->assertOk();
        $this->get('/hr-manager/tax/1721-a1/2026')->assertOk();
        $this->get('/hr-staff/attendance')->assertOk()->assertSee('Budi Santoso');
        $this->get('/supervisor/kpi')->assertOk();

        $this->post('/hr-manager/payroll', ['month' => '2026-04', 'generate' => 1])->assertRedirect();
        $this->assertDatabaseHas('payroll_periods', ['period_code' => '2026-04', 'generation_status' => 'completed']);
        $this->post('/hr-manager/payroll', ['month' => '2026-04'])->assertSessionHasErrors('month');

        $this->put("/hr-manager/employees/{$budi->id}/salary-profile", [
            'basic_salary' => 6_500_000, 'position_allowance' => 1_200_000, 'monthly_attendance_allowance' => 1_000_000,
            'overtime_hourly_rate' => 50_000, 'jkk_rate' => '0.0024', 'bank_name' => 'BCA', 'bank_account_number' => '8820192831',
            'bank_account_name' => 'Budi Santoso', 'ptkp_status' => 'K/1', 'has_bpjs_kes' => 1, 'has_jht' => 1,
        ])->assertRedirect('/hr-manager/employees');
        $this->assertSame(6_500_000, $budi->salaryProfile()->first()->basic_salary);
        $this->assertFalse($budi->salaryProfile()->first()->has_jp);

        $settings = collect(PayrollConfig::DEFINITIONS)->map(fn ($d) => $d['default'])->all();
        $settings['UMK_BEKASI_REGENCY'] = '6000000';
        $this->put('/hr-manager/payroll/settings', ['configs' => $settings])->assertSessionHas('status');
        $this->assertDatabaseHas('payroll_configs', ['config_key' => 'UMK_BEKASI_REGENCY', 'config_value' => '6000000']);

        $settings['KPI_INCENTIVE_TIERS'] = 'bukan json';
        $this->put('/hr-manager/payroll/settings', ['configs' => $settings])->assertSessionHasErrors('configs.KPI_INCENTIVE_TIERS');

        $this->post("/hr-manager/payroll/{$period->id}/approve-all")->assertSessionHas('status');
        $this->get("/hr-manager/payroll/{$period->id}/employee/{$budi->id}/pdf")->assertOk()->assertDownload();
        $this->post("/hr-manager/payroll/{$period->id}/close")->assertSessionHas('status');
    }

    public function test_halaman_karyawan(): void
    {
        $budi = $this->createBudi();
        $user = User::factory()->forEmployee($budi)->create();
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);
        app(PayslipApprovalService::class)->lockAll($period, $this->manager());
        $slip = $period->payslips()->first();

        $this->actingAs($user);
        $this->get('/dashboard')->assertRedirect('/my/payslips');
        $this->get('/my/payslips')->assertOk()->assertSee('Maret 2026')->assertSee('Notifikasi baru');
        $this->get("/my/payslips/{$slip->id}")->assertOk()->assertSee('Take Home Pay');
        $this->post('/my/notifications/read')->assertRedirect();
        $this->assertSame(0, $user->unreadNotifications()->count());
        // Tahun berjalan belum final → karyawan hanya melihat pemberitahuan, belum bisa mengunduh.
        $this->get('/my/tax-documents')->assertOk()->assertSee('belum final');
        $this->get('/my/tax-documents/2026')->assertNotFound();
    }

    public function test_halaman_atasan_divisi_konfirmasi_kpi_tim(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $atasanEmployee = Employee::factory()->create();
        $budi->update(['supervisor_id' => $atasanEmployee->id]);
        $atasan = User::factory()->role(User::ROLE_ATASAN_DIVISI)->forEmployee($atasanEmployee)->create();
        $period = $this->marchPeriod();

        $this->actingAs($atasan)->get("/supervisor/kpi/{$period->id}")->assertOk()->assertSee('Budi Santoso')->assertSee('500.000');
        $kpi = KpiScore::firstOrFail();
        $this->post("/supervisor/kpi/{$kpi->id}/confirm")->assertSessionHas('status');
        $this->assertSame($atasan->id, $kpi->refresh()->confirmed_by);
    }
}
