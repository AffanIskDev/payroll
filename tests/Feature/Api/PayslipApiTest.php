<?php

namespace Tests\Feature\Api;

use App\Models\Employee;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Modul 3B: API Slip Gaji untuk Rumatku. */
class PayslipApiTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    private Employee $budi;

    private User $budiUser;

    private Payslip $published;

    protected function setUp(): void
    {
        parent::setUp();

        $this->budi = $this->createBudi();
        $this->seedMarchActivity($this->budi);
        $this->budiUser = User::factory()->forEmployee($this->budi)->create(['email' => 'budi@rosy.test']);

        $pipeline = app(PayrollPipelineService::class);
        $march = $this->marchPeriod();
        $pipeline->generateMonthlyBatch($march);
        app(PayslipApprovalService::class)->lockAll($march, $this->manager());
        $this->published = Payslip::where('payroll_period_id', $march->id)->firstOrFail();

        // April masih draft → tidak boleh terlihat di Rumatku.
        $april = PayrollPeriod::createForMonth(2026, 4);
        $pipeline->generateMonthlyBatch($april);
    }

    public function test_tanpa_token_ditolak_401_json(): void
    {
        $this->getJson('/api/v1/employee/payslips')->assertUnauthorized();
        $this->get('/api/v1/employee/payslips')->assertUnauthorized()->assertJsonStructure(['message']);
    }

    public function test_penerbitan_token_dan_daftar_slip_hanya_yang_published(): void
    {
        $token = $this->postJson('/api/v1/auth/token', [
            'email' => 'budi@rosy.test', 'password' => 'password', 'device_name' => 'rumatku-android',
        ])->assertCreated()->json('data.access_token');

        $response = $this->withToken($token)->getJson('/api/v1/employee/payslips')->assertOk();

        $response->assertJsonPath('status', 'success')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.id', $this->published->id)
            ->assertJsonPath('data.0.period_code', '2026-03')
            ->assertJsonPath('data.0.period_name', 'Maret 2026')
            ->assertJsonPath('data.0.disbursement_date', '2026-04-01')
            ->assertJsonPath('data.0.take_home_pay', 8_485_034) // tanpa bonus manual
            ->assertJsonPath('data.0.formatted_thp', 'Rp 8.485.034')
            ->assertJsonPath('data.0.bank_name', 'BCA')
            ->assertJsonPath('data.0.bank_account_number', '8820192831')
            ->assertJsonPath('data.0.is_available', true);
    }

    public function test_password_salah_tidak_mendapat_token(): void
    {
        $this->postJson('/api/v1/auth/token', ['email' => 'budi@rosy.test', 'password' => 'salah'])
            ->assertUnprocessable();
    }

    public function test_rincian_slip_milik_sendiri(): void
    {
        Sanctum::actingAs($this->budiUser);

        $this->getJson("/api/v1/employee/payslips/{$this->published->id}")
            ->assertOk()
            ->assertJsonPath('data.employee.nik', 'EMP-2024-089')
            ->assertJsonPath('data.take_home_pay', $this->published->take_home_pay)
            ->assertJsonPath('data.transfer.bank_account_number', '8820192831')
            ->assertJsonPath('data.pdf.is_available', true)
            ->assertJsonCount(8, 'data.earnings')
            ->assertJsonCount(5, 'data.deductions');
    }

    public function test_slip_milik_orang_lain_403(): void
    {
        $other = Employee::factory()->withProfile()->create();
        Sanctum::actingAs(User::factory()->forEmployee($other)->create());

        $this->getJson("/api/v1/employee/payslips/{$this->published->id}")->assertForbidden();
        $this->getJson("/api/v1/employee/payslips/{$this->published->id}/download")->assertForbidden();
    }

    public function test_slip_draft_milik_sendiri_belum_bisa_diakses(): void
    {
        Sanctum::actingAs($this->budiUser);
        $draft = Payslip::where('employee_id', $this->budi->id)->where('status', 'draft')->firstOrFail();

        $this->getJson("/api/v1/employee/payslips/{$draft->id}")->assertNotFound();
    }

    public function test_unduh_pdf_tetap_terenkripsi_dengan_header_yang_benar(): void
    {
        Sanctum::actingAs($this->budiUser);

        $response = $this->get("/api/v1/employee/payslips/{$this->published->id}/download")->assertOk();

        $response->assertHeader('Content-Type', 'application/pdf');
        $response->assertHeader('Content-Disposition', 'inline; filename="Slip_Gaji_2026_03_EMP-2024-089.pdf"');
        $this->assertStringContainsString('/Encrypt', $response->getContent());
    }

    public function test_endpoint_karyawan_memakai_throttle_60_per_menit(): void
    {
        $route = app('router')->getRoutes()->match(request()->create('/api/v1/employee/payslips', 'GET'));

        $this->assertContains('auth:sanctum', $route->gatherMiddleware());
        $this->assertContains('throttle:60,1', $route->gatherMiddleware());
    }

    public function test_dokumen_pajak_belum_final_belum_bisa_diunduh(): void
    {
        Sanctum::actingAs($this->budiUser);

        $this->getJson('/api/v1/employee/tax-documents/2026')->assertNotFound()
            ->assertJsonPath('message', fn (string $m) => str_contains($m, 'belum final'));
        $this->getJson('/api/v1/employee/tax-documents/2019')->assertNotFound();
    }
}
