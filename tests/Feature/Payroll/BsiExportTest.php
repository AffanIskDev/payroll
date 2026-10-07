<?php

namespace Tests\Feature\Payroll;

use App\Models\Employee;
use App\Models\PayrollConfig;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Modul 5A: file Bulk Payment BSI. */
class BsiExportTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    public function test_csv_bsi_berisi_slip_final_saja_dengan_format_kolom_lengkap(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $bsiEmployee = Employee::factory()->withProfile(['bank_name' => 'BSI', 'bank_account_number' => '7099988877'])
            ->create(['full_name' => 'Siti Aminah', 'nik' => 'EMP-2020-001', 'email' => 'siti@rosy.test']);
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $pipeline = app(PayrollPipelineService::class);
        $pipeline->generateMonthlyBatch($period);

        // Hanya Budi yang di-approve; Siti Aminah masih draft → tidak ikut file.
        app(PayslipApprovalService::class)->lock($period->payslips()->where('employee_id', $budi->id)->first(), $manager);

        $response = $this->actingAs($manager)->post("/hr-manager/payroll/{$period->id}/export-bsi", [
            'debit_account' => '7001-234-567',
            'effective_date' => '2026-04-01',
        ])->assertOk();

        $response->assertHeader('Content-Type', 'text/csv; charset=UTF-8');
        $this->assertMatchesRegularExpression('/attachment; filename="BSI_PAYROLL_Maret_2026_\d{8}_\d{6}\.csv"/', $response->headers->get('Content-Disposition'));

        $lines = array_values(array_filter(explode("\r\n", $response->getContent())));
        $this->assertSame('No,Rekening Debet,Rekening Kredit,Nama Penerima,Nominal,Keterangan,Email,Jenis Transfer', $lines[0]);
        $this->assertCount(2, $lines);

        $cols = explode(',', $lines[1]);
        $this->assertSame('1', $cols[0]);
        $this->assertSame('7001234567', $cols[1]);
        $this->assertSame('8820192831', $cols[2]);
        $this->assertSame('BUDI SANTOSO', $cols[3]);
        $this->assertSame('8485034', $cols[4]);                        // integer tanpa pemisah
        $this->assertSame('Gaji Maret 2026 - EMP-2024-089', $cols[5]);
        $this->assertSame('BI-FAST', $cols[7]);                         // BCA = bank lain

        $this->assertDatabaseHas('payroll_exports', ['payroll_period_id' => $period->id, 'row_count' => 1, 'debit_account' => '7001234567']);

        // Setelah Siti di-approve: rekening BSI → INTERNAL BSI, dan pemisah pipe sesuai pengaturan.
        app(PayslipApprovalService::class)->lockAll($period->refresh(), $manager);
        PayrollConfig::create(['config_key' => 'BSI_CSV_SEPARATOR', 'config_value' => '|']);
        $content = $this->post("/hr-manager/payroll/{$period->id}/export-bsi", ['debit_account' => '7001234567', 'effective_date' => '2026-04-01'])->getContent();
        $this->assertStringContainsString('|7099988877|SITI AMINAH|', $content);
        $this->assertStringContainsString('|siti@rosy.test|INTERNAL BSI', $content);
    }

    public function test_tidak_ada_slip_final_ditolak_dengan_pesan(): void
    {
        $this->createBudi();
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);

        $this->actingAs($this->manager())
            ->post("/hr-manager/payroll/{$period->id}/export-bsi", ['debit_account' => '7001234567', 'effective_date' => '2026-04-01'])
            ->assertRedirect()
            ->assertSessionHas('error');
    }
}
