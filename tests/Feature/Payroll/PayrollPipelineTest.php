<?php

namespace Tests\Feature\Payroll;

use App\Jobs\ProcessMonthlyPayrollJob;
use App\Models\Employee;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Notifications\PayslipPublishedNotification;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use DomainException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\Storage;
use Illuminate\Validation\ValidationException;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

class PayrollPipelineTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    private function pipeline(): PayrollPipelineService
    {
        return app(PayrollPipelineService::class);
    }

    public function test_batch_draft_menghitung_seluruh_komponen_dari_sumber_data(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();

        $this->pipeline()->generateMonthlyBatch($period);

        $slip = Payslip::firstWhere('employee_id', $budi->id);
        $this->assertSame(Payslip::STATUS_DRAFT, $slip->status);
        $this->assertSame(23, $slip->attended_days);
        $this->assertSame(2, $slip->leave_sick_days);
        $this->assertSame(2, $slip->late_penalty_days);
        $this->assertSame(80_000, $slip->late_penalty_amount);
        $this->assertSame(7.0, $slip->overtime_hours);           // lembur PENDING tidak dibayar
        $this->assertSame(350_000, $slip->overtime_pay);
        $this->assertSame(500_000, $slip->kpi_incentive);         // skor 92 → tier >= 90
        $this->assertSame(240_000, $slip->tunjangan_bpjs_kes);
        $this->assertSame(374_400, $slip->tunjangan_bpjs_tk);
        $this->assertSame(100_000, $slip->other_deductions);
        $this->assertSame(9_664_400, $slip->gross_earnings);      // belum ada bonus manual
        $this->assertSame(144_966, $slip->pph21_amount);          // TER B 1,5%
        $this->assertSame(8_485_034, $slip->take_home_pay);
        $this->assertFalse($slip->is_manually_adjusted);
    }

    /** Bonus Rp 250.000 "Disetujui Manager HRD" → slip identik dengan contoh PDF. */
    public function test_penyesuaian_manual_mereproduksi_contoh_slip_persis(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstWhere('employee_id', $budi->id);

        $slip = $this->pipeline()->recalculateSinglePayslip($slip, ['additional_bonus' => 250_000], $manager->id, 'Bonus kinerja Q1 disetujui');

        $this->assertSame(6_000_000, $slip->basic_salary);
        $this->assertSame(1_200_000, $slip->position_allowance);
        $this->assertSame(1_000_000, $slip->attendance_allowance);
        $this->assertSame(250_000, $slip->additional_bonus);
        $this->assertSame(9_914_400, $slip->gross_earnings);
        $this->assertSame(80_000, $slip->late_penalty_amount);
        $this->assertSame(300_000, $slip->iuran_bpjs_kes_total);
        $this->assertSame(554_400, $slip->iuran_bpjs_tk_total);
        $this->assertSame(148_716, $slip->pph21_amount);
        $this->assertSame(1_183_116, $slip->total_deductions);
        $this->assertSame(8_731_284, $slip->take_home_pay);
        $this->assertSame('Delapan Juta Tujuh Ratus Tiga Puluh Satu Ribu Dua Ratus Delapan Puluh Empat Rupiah', $slip->terbilang);
        $this->assertSame('B', $slip->ter_category);
        $this->assertSame(1.5, $slip->ter_rate);
        $this->assertTrue($slip->is_manually_adjusted);

        $this->assertDatabaseHas('payslip_adjustments', [
            'payslip_id' => $slip->id, 'field' => 'additional_bonus', 'old_value' => '0', 'new_value' => '250000',
            'user_id' => $manager->id, 'reason' => 'Bonus kinerja Q1 disetujui',
        ]);
    }

    public function test_penyesuaian_wajib_beralasan_dan_penalti_tidak_boleh_melebihi_tunjangan_kehadiran(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstWhere('employee_id', $budi->id);

        try {
            $this->pipeline()->recalculateSinglePayslip($slip, ['additional_bonus' => 1], $this->managerId(), '');
            $this->fail('Seharusnya menolak tanpa alasan.');
        } catch (ValidationException $e) {
            $this->assertArrayHasKey('adjustmentNotes', $e->errors());
        }

        $this->expectException(ValidationException::class);
        $this->pipeline()->recalculateSinglePayslip($slip->refresh(), ['late_penalty_amount' => 1_000_001], $this->managerId(), 'uji');
    }

    public function test_generate_ulang_mempertahankan_override_manager(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstWhere('employee_id', $budi->id);
        $this->pipeline()->recalculateSinglePayslip($slip, ['additional_bonus' => 250_000, 'overtime_pay' => 400_000], $this->managerId(), 'uji');

        $this->pipeline()->generateMonthlyBatch($period->refresh());

        $slip->refresh();
        $this->assertSame(250_000, $slip->additional_bonus);
        $this->assertSame(400_000, $slip->overtime_pay);
        $this->assertSame(350_000, $slip->system_values['overtime_pay']);
    }

    public function test_override_sama_dengan_nilai_sistem_dikembalikan_ke_otomatis(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstWhere('employee_id', $budi->id);

        $slip = $this->pipeline()->recalculateSinglePayslip($slip, ['overtime_pay' => 500_000], $this->managerId(), 'uji');
        $this->assertTrue($slip->is_manually_adjusted);

        $slip = $this->pipeline()->recalculateSinglePayslip($slip, ['overtime_pay' => 350_000], $this->managerId(), 'kembali ke sistem');
        $this->assertFalse($slip->is_manually_adjusted);
        $this->assertNull($slip->overrides);
    }

    public function test_approve_lock_merender_pdf_terenkripsi_lalu_publish_dan_notifikasi(): void
    {
        Notification::fake();
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $budiUser = User::factory()->forEmployee($budi)->create();
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstWhere('employee_id', $budi->id);

        app(PayslipApprovalService::class)->lock($slip, $manager);

        $slip->refresh();
        $this->assertSame(Payslip::STATUS_PUBLISHED, $slip->status);
        $this->assertSame($manager->id, $slip->locked_by);
        $this->assertMatchesRegularExpression('#^payslips/2026/03/\d+_[a-z0-9]{20}\.pdf$#', $slip->pdf_path);
        $this->assertTrue(Hash::check('150390', $slip->pdf_password_hash));

        $disk = Storage::disk(config('payroll.disk'));
        $disk->assertExists($slip->pdf_path);
        $pdf = $disk->get($slip->pdf_path);
        $this->assertStringStartsWith('%PDF-', $pdf);
        $this->assertStringContainsString('/Encrypt', $pdf);
        $this->assertStringContainsString('/AESV2', $pdf);
        foreach (['Budi Santoso', 'EMP-2024-089', '8.485.034', '8820192831'] as $secret) {
            $this->assertStringNotContainsString($secret, $pdf, "Data pribadi '{$secret}' bocor di PDF terenkripsi");
        }

        $this->assertSame(PayrollPeriod::STATUS_PUBLISHED, $period->refresh()->status);
        $this->assertSame($manager->id, $period->approved_by);
        Notification::assertSentTo($budiUser, PayslipPublishedNotification::class);

        // Slip terkunci tidak bisa diubah lagi.
        $this->expectException(DomainException::class);
        $this->pipeline()->recalculateSinglePayslip($slip, ['additional_bonus' => 1], $manager->id, 'uji');
    }

    /** Kriteria keberterimaan 3: PDF tidak bisa dibuka tanpa 6 digit tanggal lahir. */
    public function test_pdf_hanya_terbuka_dengan_password_ddmmyy(): void
    {
        if (! is_executable('/usr/bin/pdfinfo')) {
            $this->markTestSkipped('pdfinfo (poppler-utils) tidak terpasang.');
        }

        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        app(PayslipApprovalService::class)->lockAll($period, $this->manager());

        $path = Storage::disk(config('payroll.disk'))->path(Payslip::firstWhere('employee_id', $budi->id)->pdf_path);

        exec('/usr/bin/pdfinfo '.escapeshellarg($path).' 2>&1', $out, $codeWithout);
        $this->assertNotSame(0, $codeWithout, 'PDF tidak boleh terbuka tanpa password');

        exec('/usr/bin/pdfinfo -upw 010190 '.escapeshellarg($path).' 2>&1', $out, $codeWrong);
        $this->assertNotSame(0, $codeWrong, 'Password salah harus ditolak');

        $info = [];
        exec('/usr/bin/pdfinfo -upw 150390 '.escapeshellarg($path).' 2>&1', $info, $codeRight);
        $this->assertSame(0, $codeRight, implode("\n", $info));
        $this->assertStringContainsString('AES', implode("\n", $info));
    }

    public function test_periode_terkunci_tidak_bisa_digenerate_ulang(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        app(PayslipApprovalService::class)->lockAll($period, $this->manager());

        $this->expectException(DomainException::class);
        $this->pipeline()->generateMonthlyBatch($period->refresh());
    }

    public function test_karyawan_belum_masuk_atau_sudah_resign_sebelum_periode_tidak_digaji(): void
    {
        $this->createBudi();
        Employee::factory()->withProfile()->create(['full_name' => 'Masuk April', 'join_date' => '2026-04-01']);
        Employee::factory()->withProfile()->create(['full_name' => 'Resign Februari', 'resign_date' => '2026-02-28']);
        $resignMarch = Employee::factory()->withProfile()->create(['full_name' => 'Resign Maret', 'resign_date' => '2026-03-20']);
        $period = $this->marchPeriod();

        $this->pipeline()->generateMonthlyBatch($period);

        $names = $period->payslips()->pluck('employee_name')->sort()->values()->all();
        $this->assertSame(['Budi Santoso', 'Resign Maret'], $names);
        // Bulan resign = masa pajak terakhir → rekonsiliasi Pasal 17.
        $this->assertSame('PASAL17', $period->payslips()->where('employee_id', $resignMarch->id)->value('pph21_method'));
    }

    public function test_job_batch_mencatat_progres_dan_membuang_draft_karyawan_nonaktif(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $other = Employee::factory()->withProfile()->create();
        $period = $this->marchPeriod();

        ProcessMonthlyPayrollJob::dispatchSync($period->id);
        $this->assertSame(2, $period->payslips()->count());
        $this->assertSame('completed', $period->refresh()->generation_status);
        $this->assertSame(2, $period->generation_processed);

        $other->update(['is_active' => false]);
        ProcessMonthlyPayrollJob::dispatchSync($period->id);
        $this->assertSame(1, $period->payslips()->count());
    }
}
