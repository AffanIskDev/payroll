<?php

namespace Tests\Feature\Payroll;

use App\Livewire\PayrollWorkbench;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\PayrollPipelineService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Modul 2B: workbench Manager HRD dengan hitung ulang reaktif. */
class WorkbenchTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    private Payslip $slip;

    private User $manager;

    protected function setUp(): void
    {
        parent::setUp();
        $budi = $this->createBudi();
        $this->seedMarchActivity($budi);
        $period = $this->marchPeriod();
        app(PayrollPipelineService::class)->generateMonthlyBatch($period);
        $this->slip = Payslip::firstOrFail();
        $this->manager = $this->manager();
    }

    public function test_halaman_workbench_tampil_untuk_manager(): void
    {
        $this->actingAs($this->manager)
            ->get("/hr-manager/payroll/{$this->slip->payroll_period_id}/employee/{$this->slip->employee_id}")
            ->assertOk()
            ->assertSee('Draft - Menunggu Approval')
            ->assertSee('EDITABLE', false)
            ->assertSee('Rp 8.485.034')
            ->assertSee('K/1 • TER B (1.50%)');
    }

    public function test_ubah_bonus_langsung_menghitung_ulang_thp_tanpa_menyimpan(): void
    {
        $this->actingAs($this->manager);

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])
            ->assertSee('Rp 8.485.034')
            ->set('additionalBonus', 250000)
            ->assertSee('Rp 8.731.284')
            ->assertSee('Delapan Juta Tujuh Ratus Tiga Puluh Satu Ribu Dua Ratus Delapan Puluh Empat Rupiah')
            ->assertSee('Rp 9.914.400');

        $this->assertSame(0, $this->slip->refresh()->additional_bonus, 'Belum boleh tersimpan sebelum Simpan Draft');
    }

    public function test_simpan_draft_wajib_alasan_lalu_tercatat(): void
    {
        $this->actingAs($this->manager);

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])
            ->set('additionalBonus', 250000)
            ->call('saveDraft')
            ->assertHasErrors('adjustmentNotes')
            ->set('adjustmentNotes', 'Bonus kinerja Q1')
            ->call('saveDraft')
            ->assertHasNoErrors();

        $this->assertSame(8_731_284, $this->slip->refresh()->take_home_pay);
        $this->assertDatabaseHas('payslip_adjustments', ['payslip_id' => $this->slip->id, 'field' => 'additional_bonus', 'reason' => 'Bonus kinerja Q1']);
    }

    public function test_potongan_keterlambatan_melebihi_tunjangan_kehadiran_ditolak(): void
    {
        $this->actingAs($this->manager);

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])
            ->set('latePenaltyAmount', 1_500_000)
            ->assertHasErrors('latePenaltyAmount');
    }

    public function test_approve_lock_dari_workbench(): void
    {
        $this->actingAs($this->manager);

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])
            ->set('confirmingLock', true)
            ->call('approveAndLock')
            ->assertHasNoErrors();

        $this->assertSame(Payslip::STATUS_PUBLISHED, $this->slip->refresh()->status); // queue sync di tes
    }

    public function test_penjaga_thp_negatif_tampil_dan_tombol_approve_mati(): void
    {
        $this->actingAs($this->manager);

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])
            ->assertDontSee('Belum bisa di-approve')
            ->set('otherDeductions', 20_000_000)
            ->assertSee('Belum bisa di-approve')
            ->assertSee('THP negatif')
            ->assertSeeHtml('disabled title="THP negatif');
    }

    public function test_karyawan_tidak_bisa_memakai_komponen_workbench(): void
    {
        $this->actingAs(User::factory()->create());

        Livewire::test(PayrollWorkbench::class, ['payslip' => $this->slip])->assertForbidden();
    }
}
