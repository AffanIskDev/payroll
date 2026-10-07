<?php

namespace Tests\Feature\Payroll;

use App\Exports\TaxInitialBalanceTemplateExport;
use App\Jobs\GeneratePayslipPdfJob;
use App\Jobs\ProcessMonthlyPayrollJob;
use App\Livewire\PayrollWorkbench;
use App\Models\Employee;
use App\Models\EmployeeLoan;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\KpiScore;
use App\Models\OvertimeRecord;
use App\Models\PayrollExport;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use App\Services\Payroll\Pph21CalculatorService;
use App\Services\Payroll\TaxReport1721A1Service;
use DomainException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Queue;
use Livewire\Livewire;
use RuntimeException;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Regresi untuk temuan review independen (angka = skenario reviewer). */
class ReviewRegressionTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    private function pipeline(): PayrollPipelineService
    {
        return app(PayrollPipelineService::class);
    }

    private function approval(): PayslipApprovalService
    {
        return app(PayslipApprovalService::class);
    }

    /** TINGGI 1: angka yang dikunci = angka yang tampil di workbench (data master berubah setelah draft dibuat). */
    public function test_approve_mengunci_angka_terkini_yang_tampil_di_workbench(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstOrFail();
        $this->assertSame(8_485_034, $slip->take_home_pay);

        $budi->salaryProfile->update(['basic_salary' => 7_000_000]);
        $shown = $this->pipeline()->preview($slip->fresh(), [])->take_home_pay;
        $this->assertNotSame(8_485_034, $shown);

        $this->actingAs($this->manager());
        Livewire::test(PayrollWorkbench::class, ['payslip' => $slip->fresh()])
            ->assertSee('Data berubah sejak slip ini dihitung')
            ->set('confirmingLock', true)
            ->call('approveAndLock')
            ->assertHasNoErrors();

        $slip->refresh();
        $this->assertSame(Payslip::STATUS_PUBLISHED, $slip->status);
        $this->assertSame($shown, $slip->take_home_pay);
        $this->assertSame(7_000_000, $slip->basic_salary);
        $this->assertDatabaseHas('payslip_adjustments', ['payslip_id' => $slip->id, 'field' => 'take_home_pay', 'new_value' => (string) $shown]);
    }

    /** TINGGI 2: PTKP tahun pajak = keadaan awal tahun; menikah di tengah tahun berlaku tahun berikutnya. */
    public function test_ptkp_dibekukan_per_tahun_pajak(): void
    {
        $employee = Employee::factory()->withProfile(['basic_salary' => 10_000_000])->create(['ptkp_status' => 'TK/0', 'join_date' => '2020-01-01']);

        for ($m = 1; $m <= 6; $m++) {
            $p = PayrollPeriod::createForMonth(2027, $m);
            $this->pipeline()->generateMonthlyBatch($p);
            Payslip::where('payroll_period_id', $p->id)->update(['status' => 'published']);
        }

        $employee->update(['ptkp_status' => 'K/1']); // menikah Juni

        for ($m = 7; $m <= 12; $m++) {
            $p = PayrollPeriod::createForMonth(2027, $m);
            $this->pipeline()->generateMonthlyBatch($p);
            if ($m < 12) {
                Payslip::where('payroll_period_id', $p->id)->update(['status' => 'published']);
            }
        }

        $july = Payslip::whereHas('period', fn ($q) => $q->where('period_code', '2027-07'))->firstOrFail();
        $this->assertSame('TK/0', $july->ptkp_status);
        $this->assertSame('A', $july->ter_category);

        $dec = Payslip::whereHas('period', fn ($q) => $q->where('period_code', '2027-12'))->firstOrFail();
        $b = $dec->pph21_breakdown;
        $this->assertSame('TK/0', $b['ptkp_status']);
        $this->assertSame(54_000_000, $b['ptkp']);
        $this->assertSame(intdiv($b['neto_year'] - 54_000_000, 1000) * 1000, $b['pkp']);

        // Tahun berikutnya baru memakai K/1.
        $jan = PayrollPeriod::createForMonth(2028, 1);
        $this->pipeline()->generateMonthlyBatch($jan);
        $this->assertSame('K/1', $jan->payslips()->value('ptkp_status'));
    }

    /** TINGGI 3: ekspor BSI idempoten — slip yang sudah diekspor tidak masuk file berikutnya. */
    public function test_ekspor_bsi_tidak_menggandakan_slip(): void
    {
        $budi = $this->createBudi();
        Employee::factory()->withProfile(['bank_name' => 'BSI', 'bank_account_number' => '7099988877'])->create(['full_name' => 'Siti Aminah']);
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $this->pipeline()->generateMonthlyBatch($period);
        $this->approval()->lock($period->payslips()->where('employee_id', $budi->id)->first(), $manager);

        $payload = ['debit_account' => '7001234567', 'effective_date' => '2026-04-01'];
        $first = $this->actingAs($manager)->post("/hr-manager/payroll/{$period->id}/export-bsi", $payload)->assertOk()->getContent();
        $this->approval()->lockAll($period->refresh(), $manager);
        $second = $this->post("/hr-manager/payroll/{$period->id}/export-bsi", $payload)->assertOk()->getContent();

        $this->assertStringContainsString('8820192831', $first);
        $this->assertStringNotContainsString('8820192831', $second);
        $this->assertStringContainsString('7099988877', $second);
        $this->assertSame((int) $period->payslips()->sum('take_home_pay'), (int) PayrollExport::sum('total_amount'));

        // Ekspor ketiga tanpa slip baru ditolak; ekspor ulang eksplisit memuat semua.
        $this->post("/hr-manager/payroll/{$period->id}/export-bsi", $payload)->assertRedirect()->assertSessionHas('error');
        $again = $this->post("/hr-manager/payroll/{$period->id}/export-bsi", $payload + ['include_exported' => 1])->assertOk()->getContent();
        $this->assertStringContainsString('8820192831', $again);
        $this->assertStringContainsString('7099988877', $again);
    }

    /** SEDANG 4: masa pajak terakhir tidak bisa dikunci selama bulan sebelumnya masih draft; setelahnya cocok dengan 1721-A1. */
    public function test_desember_menunggu_november_final_dan_dihitung_ulang_saat_dikunci(): void
    {
        $employee = Employee::factory()->withProfile([
            'basic_salary' => 7_000_000, 'position_allowance' => 1_000_000, 'monthly_attendance_allowance' => 500_000,
        ])->create(['ptkp_status' => 'K/1']);
        $manager = $this->manager();

        $oct = PayrollPeriod::createForMonth(2026, 10);
        $this->pipeline()->generateMonthlyBatch($oct);
        $this->approval()->lockAll($oct, $manager);
        $nov = PayrollPeriod::createForMonth(2026, 11);
        $this->pipeline()->generateMonthlyBatch($nov);
        $dec = PayrollPeriod::createForMonth(2026, 12);
        $this->pipeline()->generateMonthlyBatch($dec);

        $result = $this->approval()->lockAll($dec->refresh(), $manager);
        $this->assertSame(0, $result['locked']);
        $this->assertStringContainsString('November 2026', implode(' ', $result['skipped']));

        $novSlip = $nov->payslips()->firstOrFail();
        $this->pipeline()->recalculateSinglePayslip($novSlip, ['additional_bonus' => 20_000_000], $manager->id, 'Bonus akhir tahun');
        $this->approval()->lockAll($nov->refresh(), $manager);
        $this->assertSame(1, $this->approval()->lockAll($dec->refresh(), $manager)['locked']);

        $decSlip = $dec->payslips()->firstOrFail();
        $report = app(TaxReport1721A1Service::class)->generateAnnualReport($employee, 2026);
        $this->assertSame($report['lines'][22], $decSlip->pph21_amount);
        $this->assertSame([], $report['warnings']);
    }

    /** SEDANG 5: saldo awal yang tumpang tindih dengan slip sistem ditolak saat impor dan memblokir masa terakhir. */
    public function test_saldo_awal_tumpang_tindih_ditolak_dan_memblokir_desember(): void
    {
        $employee = Employee::factory()->withProfile(['basic_salary' => 8_000_000])->create(['ptkp_status' => 'TK/0', 'nik' => 'EMP-X-001']);
        $manager = $this->manager();
        $mar = PayrollPeriod::createForMonth(2026, 3);
        $this->pipeline()->generateMonthlyBatch($mar);
        $this->approval()->lockAll($mar, $manager);

        $csv = tempnam(sys_get_temp_dir(), 'ytd').'.csv';
        file_put_contents($csv, "nik,tahun,cutoff,ptkp,bruto,jhtjp,bj,pph,notes\nEMP-X-001,2026,3,TK/0,27000000,720000,1350000,600000,\n");
        $this->artisan('payroll:import-ytd', ['filepath' => $csv, '--dry-run' => true])
            ->expectsOutputToContain('cut-off saldo awal maksimal 2')
            ->assertExitCode(1);
        unlink($csv);

        // Bila data dobel tetap masuk (mis. lewat database langsung), masa terakhir tidak boleh dikunci.
        EmployeeTaxInitialBalance::create([
            'employee_id' => $employee->id, 'tax_year' => 2026, 'cutoff_month' => 3, 'ptkp_status' => 'TK/0',
            'gross_income_ytd' => 27_000_000, 'employee_jht_jp_ytd' => 720_000, 'pph21_paid_ytd' => 600_000,
        ]);
        $dec = PayrollPeriod::createForMonth(2026, 12);
        $this->pipeline()->generateMonthlyBatch($dec);
        $result = $this->approval()->lockAll($dec, $manager);

        $this->assertSame(0, $result['locked']);
        $this->assertStringContainsString('terhitung dua kali', implode(' ', $result['skipped']));
        $this->assertNotEmpty(app(TaxReport1721A1Service::class)->generateAnnualReport($employee, 2026)['warnings']);
    }

    /** SEDANG 6: workbench tidak menimpa nilai sistem hasil generate ulang (lost update). */
    public function test_workbench_tidak_menimpa_hasil_generate_ulang(): void
    {
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstOrFail();
        $this->actingAs($this->manager());

        $lw = Livewire::test(PayrollWorkbench::class, ['payslip' => $slip]);

        $this->travel(5)->seconds();
        OvertimeRecord::create(['employee_id' => $budi->id, 'work_date' => '2026-03-30', 'hours' => 4, 'status' => 'APPROVED']);
        $this->pipeline()->generateMonthlyBatch($period->fresh());
        $this->assertSame(550_000, $slip->fresh()->overtime_pay);

        // Simpan pertama ditolak karena slip berubah sejak dibuka; nilai terbaru dimuat.
        $lw->set('additionalBonus', 250000)->set('adjustmentNotes', 'Bonus Q1')->call('saveDraft')
            ->assertHasErrors('general')
            ->assertSet('overtimePay', 550000);

        // Diulang: hanya bonus yang dikirim; lembur tetap nilai sistem terbaru.
        $lw->set('additionalBonus', 250000)->set('adjustmentNotes', 'Bonus Q1')->call('saveDraft')->assertHasNoErrors();
        $slip->refresh();
        $this->assertSame(550_000, $slip->overtime_pay);
        $this->assertSame(250_000, $slip->additional_bonus);
        $this->assertArrayNotHasKey('overtime_pay', $slip->overrides ?? []);
    }

    /** SEDANG 7: karyawan resign yang sudah dinonaktifkan tetap mendapat slip bulan resign (masa pajak terakhir). */
    public function test_resign_dan_dinonaktifkan_tetap_mendapat_slip_terakhir(): void
    {
        $this->createBudi();
        $resign = Employee::factory()->withProfile()->create(['resign_date' => '2026-03-20', 'is_active' => false]);
        Employee::factory()->withProfile()->create(['resign_date' => '2026-02-10', 'is_active' => false]);
        $period = $this->marchPeriod();

        $this->pipeline()->generateMonthlyBatch($period);

        $this->assertSame(2, $period->payslips()->count());
        $this->assertSame('PASAL17', $period->payslips()->where('employee_id', $resign->id)->value('pph21_method'));
    }

    /** SEDANG 8: Atasan Divisi tanpa tautan karyawan tidak melihat/konfirmasi KPI siapa pun. */
    public function test_atasan_tanpa_tautan_karyawan_tidak_punya_tim(): void
    {
        $boss = Employee::factory()->withProfile()->create(['full_name' => 'Direktur Rahasia', 'is_management' => true]);
        $period = PayrollPeriod::createForMonth(2026, 3);
        $kpi = KpiScore::create(['employee_id' => $boss->id, 'period_code' => '2026-03', 'score' => 95, 'incentive_amount' => 7_500_000]);
        $atasan = User::factory()->role(User::ROLE_ATASAN_DIVISI)->create();

        $this->actingAs($atasan)->get("/supervisor/kpi/{$period->id}")->assertOk()->assertDontSee('Direktur Rahasia');
        $this->post("/supervisor/kpi/{$kpi->id}/confirm")->assertForbidden();
        $this->assertNull($kpi->fresh()->confirmed_by);
    }

    /** RENDAH 9: satu data rusak tidak menggagalkan batch; catatan kasbon panjang tersimpan. */
    public function test_data_rusak_satu_karyawan_tidak_menghentikan_batch(): void
    {
        $a = Employee::factory()->withProfile()->create(['full_name' => 'Karyawan A']);
        Employee::factory()->withProfile()->create(['full_name' => 'Data Rusak', 'ptkp_status' => 'K/I/1']);
        $c = Employee::factory()->withProfile()->create(['full_name' => 'Karyawan C']);
        foreach (range(1, 3) as $i) {
            EmployeeLoan::create(['employee_id' => $c->id, 'description' => "Pinjaman koperasi karyawan untuk biaya pendidikan anak tahun ajaran baru angsuran ke-{$i}",
                'installment_amount' => 100_000, 'start_period' => '2026-01', 'installments_total' => 12]);
        }
        $period = PayrollPeriod::createForMonth(2026, 3);

        ProcessMonthlyPayrollJob::dispatchSync($period->id);

        $period->refresh();
        $this->assertSame('completed', $period->generation_status);
        $this->assertSame(2, $period->payslips()->count());
        $this->assertStringContainsString('Data Rusak', (string) $period->generation_error);
        $this->assertGreaterThan(255, mb_strlen((string) $period->payslips()->where('employee_id', $c->id)->value('other_deductions_note')));
        $this->assertSame(1, $period->payslips()->where('employee_id', $a->id)->count());
    }

    /** RENDAH 10: bulan kerja dari saldo awal dimulai bulan masuk, bukan Januari. */
    public function test_bulan_kerja_saldo_awal_mengikuti_tanggal_masuk(): void
    {
        $e = Employee::factory()->create(['ptkp_status' => 'TK/0', 'join_date' => '2026-02-16']);
        EmployeeTaxInitialBalance::create([
            'employee_id' => $e->id, 'tax_year' => 2026, 'cutoff_month' => 2, 'ptkp_status' => 'TK/0',
            'gross_income_ytd' => 30_000_000, 'employee_jht_jp_ytd' => 0, 'pph21_paid_ytd' => 0,
        ]);

        $r = app(Pph21CalculatorService::class)->reconcile(PayrollPeriod::createForMonth(2026, 12), $e, 30_000_000, 0);

        $this->assertSame(2, $r['months_worked']); // Februari (saldo awal) + Desember
        $this->assertSame(1_000_000, $r['biaya_jabatan_cap']);
    }

    /** RENDAH 11: THP negatif tidak bisa di-approve. */
    public function test_thp_negatif_tidak_bisa_dikunci(): void
    {
        $this->createBudi();
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = $this->pipeline()->recalculateSinglePayslip(Payslip::firstOrFail(), ['other_deductions' => 20_000_000], $manager->id, 'Pelunasan kasbon');
        $this->assertLessThan(0, $slip->take_home_pay);

        try {
            $this->approval()->lock($slip, $manager);
            $this->fail('THP negatif seharusnya ditolak.');
        } catch (DomainException $e) {
            $this->assertStringContainsString('THP negatif', $e->getMessage());
        }
        $this->assertSame(Payslip::STATUS_DRAFT, $slip->fresh()->status);
    }

    /** RENDAH 12–13: unggahan .txt ditolak dengan pesan validasi; template tidak memuat data pajak karyawan. */
    public function test_unggah_txt_ditolak_dan_template_berisi_contoh_fiktif(): void
    {
        $this->createBudi();
        $file = UploadedFile::fake()->createWithContent('saldo.txt', "nik,tahun\nEMP-2024-089,2026\n");

        $this->actingAs($this->manager())->post('/hr-manager/payroll/import-ytd/validate', ['file' => $file])
            ->assertSessionHasErrors('file');

        $rows = (new TaxInitialBalanceTemplateExport)->array();
        $this->assertStringStartsWith('EMP-CONTOH', $rows[0][0]);
    }

    /** RENDAH 14: antrean — retry_after > timeout batch; PDF gagal tercatat dan bisa dibuat ulang. */
    public function test_operasional_antrean(): void
    {
        $this->assertGreaterThan((new ProcessMonthlyPayrollJob(1))->timeout, config('queue.connections.database.retry_after'));

        $this->createBudi();
        $period = $this->marchPeriod();
        $manager = $this->manager();
        $this->pipeline()->generateMonthlyBatch($period);
        $slip = Payslip::firstOrFail();
        Payslip::whereKey($slip->id)->update(['status' => Payslip::STATUS_LOCKED]);

        (new GeneratePayslipPdfJob($slip->id))->failed(new RuntimeException('dompdf kehabisan memori'));
        $this->assertSame('dompdf kehabisan memori', $slip->fresh()->pdf_error);

        Queue::fake();
        $this->actingAs($manager)->post("/hr-manager/payroll/{$period->id}/retry-pdf")->assertSessionHas('status');
        Queue::assertPushed(GeneratePayslipPdfJob::class, 1);
    }
}
