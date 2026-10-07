<?php

namespace Tests\Concerns;

use App\Models\AttendanceLog;
use App\Models\Employee;
use App\Models\EmployeeLoan;
use App\Models\KpiScore;
use App\Models\OvertimeRecord;
use App\Models\PayrollPeriod;
use App\Models\User;
use Illuminate\Support\Carbon;

/**
 * Menyusun ulang data "Budi Santoso" dari Visual Sample Slip Gaji Karyawan.pdf
 * (Maret 2026, THP Rp 8.731.284).
 */
trait BuildsSamplePayroll
{
    protected function createBudi(array $overrides = []): Employee
    {
        return Employee::factory()->withProfile([
            'basic_salary' => 6_000_000,
            'position_allowance' => 1_200_000,
            'monthly_attendance_allowance' => 1_000_000,
            'overtime_hourly_rate' => 50_000,
            'bank_name' => 'BCA',
            'bank_account_number' => '8820192831',
            'bank_account_name' => 'BUDI SANTOSO',
        ])->create($overrides + [
            'nik' => 'EMP-2024-089',
            'full_name' => 'Budi Santoso',
            'birth_date' => '1990-03-15',
            'ptkp_status' => 'K/1',
            'department' => 'Keuangan',
            'position' => 'Staff Finance',
            'employment_status' => 'PKWTT (Tetap)',
        ]);
    }

    /** 23 hadir (2 hari terlambat 62 & 63 menit), 2 izin/sakit, lembur 7 jam, KPI 92, kasbon 100rb. */
    protected function seedMarchActivity(Employee $employee): void
    {
        $day = Carbon::parse('2026-03-02');
        $records = 0;
        while ($records < 25) {
            if (! $day->isSunday()) {
                $records++;
                AttendanceLog::create([
                    'employee_id' => $employee->id,
                    'work_date' => $day->toDateString(),
                    'status' => match ($records) {
                        10 => 'IZIN',
                        18 => 'SAKIT',
                        default => 'HADIR',
                    },
                    'late_minutes' => match ($records) {
                        4 => 62,
                        12 => 63,
                        default => 0,
                    },
                ]);
            }
            $day->addDay();
        }

        OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => '2026-03-14', 'hours' => 4, 'status' => 'APPROVED']);
        OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => '2026-03-21', 'hours' => 3, 'status' => 'APPROVED']);
        OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => '2026-03-28', 'hours' => 5, 'status' => 'PENDING']);

        KpiScore::create(['employee_id' => $employee->id, 'period_code' => '2026-03', 'score' => 92]);

        EmployeeLoan::create([
            'employee_id' => $employee->id,
            'description' => 'Cicilan Pinjaman Internal',
            'installment_amount' => 100_000,
            'start_period' => '2026-01',
            'installments_total' => 12,
        ]);
    }

    protected function marchPeriod(): PayrollPeriod
    {
        return PayrollPeriod::createForMonth(2026, 3);
    }

    protected function manager(): User
    {
        return User::factory()->managerHrd()->create(['name' => 'Siti Nurhaliza']);
    }

    private ?User $sampleManager = null;

    protected function managerId(): int
    {
        return ($this->sampleManager ??= $this->manager())->id;
    }
}
