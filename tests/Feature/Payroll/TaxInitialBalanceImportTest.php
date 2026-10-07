<?php

namespace Tests\Feature\Payroll;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

/** Modul 4A: impor saldo awal pajak YTD. */
class TaxInitialBalanceImportTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    private function csv(array $rows, string $sep = ','): string
    {
        $header = 'employee_id / NIK,tax_year,cutoff_month,ptkp_status,gross_income_ytd,employee_jht_jp_ytd,biaya_jabatan_ytd,pph21_paid_ytd,notes';
        $lines = [$sep === ',' ? $header : str_replace(',', $sep, $header)];
        foreach ($rows as $r) {
            $lines[] = implode($sep, $r);
        }
        $path = tempnam(sys_get_temp_dir(), 'ytd').'.csv';
        file_put_contents($path, implode("\n", $lines)."\n");

        return $path;
    }

    public function test_command_mengimpor_baris_valid_dan_melaporkan_nik_yang_tidak_ada(): void
    {
        $this->createBudi();
        $path = $this->csv([
            ['EMP-2024-089', '2026', '9', 'K/1', '81000000', '1620000', '4050000', '900000', 'Sistem lama'],
            ['EMP-9999-999', '2026', '9', 'TK/0', '1', '1', '1', '1', ''],
        ]);

        $this->artisan('payroll:import-ytd', ['filepath' => $path])
            ->expectsOutputToContain('Total baris: 2')
            ->expectsOutputToContain('NIK EMP-9999-999 tidak ditemukan')
            ->expectsOutputToContain('Tersimpan: 1')
            ->assertExitCode(1);

        $balance = EmployeeTaxInitialBalance::firstOrFail();
        $this->assertSame(81_000_000, $balance->gross_income_ytd);
        $this->assertSame(9, $balance->cutoff_month);
        $this->assertSame('K/1', $balance->ptkp_status);
    }

    public function test_dry_run_dan_strict_tidak_menyimpan_apa_pun(): void
    {
        $this->createBudi();
        $path = $this->csv([
            ['EMP-2024-089', '2026', '12', 'K/9', 'abc', '0', '0', '0', ''],
        ]);

        $this->artisan('payroll:import-ytd', ['filepath' => $path, '--dry-run' => true])
            ->expectsOutputToContain('Bulan cut-off harus bilangan bulat 1 s/d 11. Status PTKP harus salah satu dari')
            ->assertExitCode(1);

        $this->assertSame(0, EmployeeTaxInitialBalance::count());
    }

    public function test_impor_ulang_memperbarui_bukan_menggandakan_dan_format_indonesia_diterima(): void
    {
        $this->createBudi();
        $this->artisan('payroll:import-ytd', ['filepath' => $this->csv([['EMP-2024-089', '2026', '8', 'K/1', '1', '1', '1', '1', '']])]);
        $this->artisan('payroll:import-ytd', ['filepath' => $this->csv([['EMP-2024-089', '2026', '9', 'k1', '"81.000.000"', '1620000', '4050000', '900000', 'koreksi']], ';')])
            ->assertExitCode(0);

        $this->assertSame(1, EmployeeTaxInitialBalance::count());
        $this->assertSame(81_000_000, EmployeeTaxInitialBalance::first()->gross_income_ytd);
        $this->assertSame(9, EmployeeTaxInitialBalance::first()->cutoff_month);
    }

    public function test_halaman_upload_validasi_dulu_lalu_simpan(): void
    {
        $this->createBudi();
        Employee::factory()->create(['nik' => 'EMP-2010-002']);
        $manager = $this->manager();
        $good = $this->csv([
            ['EMP-2024-089', '2026', '9', 'K/1', '81000000', '1620000', '4050000', '900000', ''],
            ['EMP-2010-002', '2026', '9', 'TK/0', '60000000', '1200000', '3000000', '600000', ''],
        ]);

        $this->actingAs($manager)
            ->post('/hr-manager/payroll/import-ytd/validate', ['file' => new UploadedFile($good, 'saldo.csv', 'text/csv', null, true)])
            ->assertRedirect('/hr-manager/payroll/import-ytd')
            ->assertSessionHas('ytd_result', fn ($r) => $r['can_commit'] && count($r['valid']) === 2);
        $this->assertSame(0, EmployeeTaxInitialBalance::count(), 'Validasi belum boleh menyimpan');

        $this->post('/hr-manager/payroll/import-ytd/commit')->assertSessionHas('status');
        $this->assertSame(2, EmployeeTaxInitialBalance::count());

        $bad = $this->csv([['EMP-0000-000', '2026', '9', 'K/1', '1', '1', '1', '1', '']]);
        $this->post('/hr-manager/payroll/import-ytd/validate', ['file' => new UploadedFile($bad, 'salah.csv', 'text/csv', null, true)])
            ->assertSessionHas('ytd_result', fn ($r) => ! $r['can_commit'] && count($r['errors']) === 1);

        $this->get('/hr-manager/payroll/import-ytd')->assertOk()->assertSee('tidak ditemukan');
        $this->get('/hr-manager/payroll/import-ytd/template')->assertOk()->assertDownload('template_saldo_awal_pajak_ytd.xlsx');
    }
}
