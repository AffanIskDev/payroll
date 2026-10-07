<?php

namespace Tests\Feature\Payroll;

use App\Models\PayrollPeriod;
use App\Services\Payroll\PayslipApprovalService;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\BuildsSamplePayroll;
use Tests\TestCase;

class GeneratePayrollCommandTest extends TestCase
{
    use BuildsSamplePayroll, RefreshDatabase;

    public function test_membuat_periode_dan_generate_draft(): void
    {
        $this->createBudi();

        $this->artisan('payroll:generate', ['period' => '2026-03', '--sync' => true])
            ->expectsOutputToContain('Maret 2026: 1 karyawan diproses')
            ->assertExitCode(0);

        $period = PayrollPeriod::firstWhere('period_code', '2026-03');
        $this->assertSame('2026-04-01', $period->payment_date->toDateString());
        $this->assertSame(1, $period->payslips()->count());
    }

    public function test_periode_terkunci_dan_format_salah_ditolak(): void
    {
        $this->createBudi();
        $this->artisan('payroll:generate', ['period' => '2026-03', '--sync' => true]);
        app(PayslipApprovalService::class)->lockAll(PayrollPeriod::first(), $this->manager());

        $this->artisan('payroll:generate', ['period' => '2026-03'])->assertExitCode(1);
        $this->artisan('payroll:generate', ['period' => '2026-13'])->assertExitCode(1);
    }

    public function test_terjadwal_di_hari_terakhir_bulan(): void
    {
        $event = collect(app(Schedule::class)->events())
            ->first(fn ($e) => str_contains($e->command ?? '', 'payroll:generate'));

        $this->assertNotNull($event);
        // Laravel menghitung tanggal terakhir bulan berjalan setiap kali scheduler di-boot.
        $this->assertSame('0 20 '.now('Asia/Jakarta')->endOfMonth()->day.' * *', $event->expression);
    }
}
