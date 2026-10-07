<?php

namespace Database\Seeders;

use App\Models\AttendanceLog;
use App\Models\Employee;
use App\Models\EmployeeLoan;
use App\Models\EmployeeSalaryProfile;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\KpiScore;
use App\Models\OvertimeRecord;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\BpjsCalculatorService;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use App\Services\Payroll\Pph21TerCalculatorService;
use App\Support\Money;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;

/**
 * Data demo: 12 karyawan fiktif, go-live sistem Maret 2026 (saldo awal YTD
 * Januari–Februari diimpor), periode Maret–Agustus sudah terbit, September
 * masih draft menunggu approval. "Budi Santoso" Maret 2026 identik dengan
 * Visual Sample Slip Gaji Karyawan.pdf (THP Rp 8.731.284).
 */
class DemoPayrollSeeder extends Seeder
{
    public const PASSWORD = 'password';

    /** Libur nasional bertanggal tetap yang dipakai demo (+ Nyepi 2026). */
    private const HOLIDAYS = ['2026-03-19', '2026-05-01', '2026-06-01', '2026-08-17'];

    private const PUBLISHED_MONTHS = [3, 4, 5, 6, 7, 8];

    private const DRAFT_MONTH = 9;

    /**
     * nik, nama, lahir, jk, ptkp, divisi, jabatan, status kerja, manajemen, pokok, tunj. jabatan,
     * tunj. kehadiran, tarif lembur/jam, bank, rekening, peran login, atasan (nik), pola
     */
    private const EMPLOYEES = [
        ['EMP-2019-012', 'Siti Nurhaliza', '1985-07-22', 'P', 'K/2', 'HRD', 'Manager HRD & Personalia', 'PKWTT (Tetap)', true, 15_000_000, 4_000_000, 1_500_000, 0, 'BSI', '7012345678', User::ROLE_MANAGER_HRD, null, 'disiplin'],
        ['EMP-2016-005', 'Rudi Hartono', '1980-12-01', 'L', 'K/3', 'Keuangan', 'Manager Keuangan', 'PKWTT (Tetap)', true, 22_000_000, 5_000_000, 1_500_000, 0, 'BCA', '1122334455', User::ROLE_KARYAWAN, null, 'disiplin'],
        ['EMP-2018-007', 'Hendra Gunawan', '1982-11-30', 'L', 'K/3', 'Pelayanan', 'Kepala Divisi Pelayanan', 'PKWTT (Tetap)', true, 11_000_000, 2_500_000, 1_000_000, 0, 'BCA', '5410987654', User::ROLE_ATASAN_DIVISI, null, 'disiplin'],
        ['EMP-2024-089', 'Budi Santoso', '1990-03-15', 'L', 'K/1', 'Keuangan', 'Staff Finance', 'PKWTT (Tetap)', false, 6_000_000, 1_200_000, 1_000_000, 50_000, 'BCA', '8820192831', User::ROLE_KARYAWAN, 'EMP-2016-005', 'normal'],
        ['EMP-2022-041', 'Rina Wulandari', '1997-04-09', 'P', 'TK/0', 'HRD', 'Staff HRD', 'PKWTT (Tetap)', false, 5_200_000, 500_000, 750_000, 35_000, 'MANDIRI', '1230009876543', User::ROLE_STAFF_HRD, 'EMP-2019-012', 'normal'],
        ['EMP-2023-118', 'Andi Pratama', '1995-01-30', 'L', 'TK/1', 'Pelayanan', 'Perawat Luka', 'PKWTT (Tetap)', false, 5_500_000, 600_000, 800_000, 40_000, 'BRI', '012301000123456', User::ROLE_KARYAWAN, 'EMP-2018-007', 'normal'],
        ['EMP-2021-064', 'Fitri Handayani', '1993-08-17', 'P', 'K/0', 'Pelayanan', 'Perawat Luka', 'PKWTT (Tetap)', false, 5_938_885, 600_000, 800_000, 40_000, 'BSI', '7023456789', User::ROLE_KARYAWAN, 'EMP-2018-007', 'normal'],
        ['EMP-2025-201', 'Dewi Lestari', '1998-11-02', 'P', 'TK/0', 'Pelayanan', 'Staff Administrasi', 'PKWT (Kontrak)', false, 4_500_000, 0, 600_000, 30_000, 'BSI', '7034567890', User::ROLE_KARYAWAN, 'EMP-2018-007', 'normal'],
        ['EMP-2020-033', 'Agus Setiawan', '1988-06-05', 'L', 'K/2', 'Logistik', 'Driver & Kurir', 'PKWTT (Tetap)', false, 4_800_000, 300_000, 700_000, 35_000, 'BRI', '012302000654321', User::ROLE_KARYAWAN, 'EMP-2016-005', 'lembur'],
        ['EMP-2022-077', 'Maya Sari', '1994-02-14', 'P', 'TK/2', 'Marketing', 'Staff Marketing', 'PKWTT (Tetap)', false, 7_000_000, 800_000, 800_000, 45_000, 'BNI', '0987654321', User::ROLE_KARYAWAN, null, 'normal'],
        ['EMP-2021-052', 'Joko Susilo', '1996-09-21', 'L', 'TK/0', 'IT', 'Staff IT', 'PKWTT (Tetap)', false, 8_500_000, 1_000_000, 900_000, 60_000, 'BCA', '6789012345', User::ROLE_KARYAWAN, null, 'sering_telat'],
        ['EMP-2010-002', 'Lina Marlina', '1966-05-10', 'P', 'K/1', 'Logistik', 'Admin Gudang', 'PKWTT (Tetap)', false, 5_000_000, 400_000, 700_000, 35_000, 'MANDIRI', '1230001112223', User::ROLE_KARYAWAN, 'EMP-2016-005', 'normal'],
    ];

    /** @var array<string, Employee> */
    private array $employees = [];

    public function run(): void
    {
        // PDF slip dirender langsung saat seeding, tidak lewat queue worker.
        config(['queue.default' => 'sync']);
        mt_srand(20260306);

        $this->createEmployees();
        $this->createLoans();
        $this->createInitialTaxBalances();

        foreach ([...self::PUBLISHED_MONTHS, self::DRAFT_MONTH] as $month) {
            $this->createActivity($month);
        }

        $manager = User::where('role', User::ROLE_MANAGER_HRD)->firstOrFail();
        $pipeline = app(PayrollPipelineService::class);
        $approval = app(PayslipApprovalService::class);

        foreach (self::PUBLISHED_MONTHS as $month) {
            $period = PayrollPeriod::createForMonth(2026, $month, $manager);
            $pipeline->generateMonthlyBatch($period);
            $period->update(['generation_status' => 'completed', 'generated_at' => $period->end_date->copy()->addDay()->setTime(9, 0)]);

            if ($month === 3) {
                // Bonus tambahan "Disetujui Manager HRD" seperti contoh slip.
                $budi = Payslip::where('payroll_period_id', $period->id)->where('employee_nik', 'EMP-2024-089')->firstOrFail();
                $pipeline->recalculateSinglePayslip($budi, ['additional_bonus' => 250_000], $manager->id, 'Bonus kinerja Q1 disetujui Direksi');
            }

            $approval->lockAll($period->refresh(), $manager);
            if ($month !== 8) {
                $approval->close($period->refresh(), $manager);
            }
            $this->command?->info("Periode {$period->period_name}: ".$period->payslips()->count().' slip terbit.');
        }

        $september = PayrollPeriod::createForMonth(2026, self::DRAFT_MONTH, $manager);
        $pipeline->generateMonthlyBatch($september);
        $september->update(['generation_status' => 'completed', 'generated_at' => now()]);
        $this->command?->info('Periode September 2026: draft menunggu approval.');
    }

    private function createEmployees(): void
    {
        foreach (self::EMPLOYEES as $row) {
            [$nik, $name, $birth, $gender, $ptkp, $dept, $position, $status, $mgmt, $basic, $posAllow,
                $attAllow, $otRate, $bank, $account, $role] = $row;

            $employee = Employee::create([
                'nik' => $nik,
                'full_name' => $name,
                'email' => $this->email($name),
                'phone' => '08'.mt_rand(1100000000, 1399999999),
                'birth_date' => $birth,
                'gender' => $gender,
                'ptkp_status' => $ptkp,
                'npwp' => null,
                'national_id' => '3216'.substr(str_replace('-', '', $birth), 2).sprintf('%06d', mt_rand(1, 999999)),
                'address' => 'Kabupaten Bekasi, Jawa Barat',
                'department' => $dept,
                'position' => $position,
                'employment_status' => $status,
                'is_management' => $mgmt,
                'join_date' => '20'.substr($nik, 6, 2).'-01-02',
                'is_active' => true,
            ]);

            EmployeeSalaryProfile::create([
                'employee_id' => $employee->id,
                'basic_salary' => $basic,
                'position_allowance' => $posAllow,
                'monthly_attendance_allowance' => $attAllow,
                'overtime_hourly_rate' => $otRate,
                'has_bpjs_kes' => true,
                'has_jkk' => true,
                'has_jkm' => true,
                'has_jht' => true,
                // Usia di atas batas usia pensiun tidak bisa menjadi peserta baru JP.
                'has_jp' => $nik !== 'EMP-2010-002',
                'jkk_rate' => $dept === 'Logistik' ? 0.0054 : 0.0024,
                'bank_name' => $bank,
                'bank_account_number' => $account,
                'bank_account_name' => mb_strtoupper($name),
            ]);

            User::create([
                'name' => $name,
                'email' => $this->email($name),
                'password' => self::PASSWORD,
                'role' => $role,
                'employee_id' => $employee->id,
                'email_verified_at' => now(),
            ]);

            $this->employees[$nik] = $employee;
        }

        foreach (self::EMPLOYEES as $row) {
            if ($row[16]) {
                $this->employees[$row[0]]->update(['supervisor_id' => $this->employees[$row[16]]->id]);
            }
        }
    }

    private function createLoans(): void
    {
        EmployeeLoan::create(['employee_id' => $this->employees['EMP-2024-089']->id, 'description' => 'Cicilan Pinjaman Internal', 'installment_amount' => 100_000, 'start_period' => '2026-01', 'installments_total' => 12]);
        EmployeeLoan::create(['employee_id' => $this->employees['EMP-2020-033']->id, 'description' => 'Kasbon Renovasi Rumah', 'installment_amount' => 150_000, 'start_period' => '2026-05', 'installments_total' => 6]);
        EmployeeLoan::create(['employee_id' => $this->employees['EMP-2025-201']->id, 'description' => 'Kasbon Biaya Pengobatan', 'installment_amount' => 200_000, 'start_period' => '2026-08', 'installments_total' => 3]);
    }

    /** Saldo awal Januari–Februari 2026 dari sistem lama (seolah hasil impor Modul 4A). */
    private function createInitialTaxBalances(): void
    {
        $bpjs = app(BpjsCalculatorService::class);
        $ter = app(Pph21TerCalculatorService::class);

        foreach ($this->employees as $employee) {
            $profile = $employee->salaryProfile;
            $b = $bpjs->calculate($profile->basic_salary, $profile);
            $gross = $profile->basic_salary + $profile->position_allowance + $profile->monthly_attendance_allowance
                + $b['tunjangan_bpjs_kes'] + $b['tunjangan_bpjs_tk'] + 300_000;
            $pph = $ter->calculate($gross, $employee->ptkp_status)['amount'];

            EmployeeTaxInitialBalance::create([
                'employee_id' => $employee->id,
                'tax_year' => 2026,
                'cutoff_month' => 2,
                'ptkp_status' => $employee->ptkp_status,
                'gross_income_ytd' => 2 * $gross,
                'employee_jht_jp_ytd' => 2 * $b['employee_jht_jp'],
                'biaya_jabatan_ytd' => 2 * min(Money::pctBp($gross, 500), 500_000),
                'pph21_paid_ytd' => 2 * $pph,
                'notes' => 'Impor saldo awal dari sistem payroll lama (Jan–Feb 2026)',
            ]);
        }
    }

    private function createActivity(int $month): void
    {
        $start = Carbon::create(2026, $month, 1);
        $periodCode = $start->format('Y-m');
        $days = collect();
        for ($d = $start->copy(); $d->month === $month; $d->addDay()) {
            if (! $d->isSunday() && ! in_array($d->toDateString(), self::HOLIDAYS, true)) {
                $days->push($d->copy());
            }
        }

        $hendra = User::where('email', $this->email('Hendra Gunawan'))->first();

        foreach (self::EMPLOYEES as $row) {
            $nik = $row[0];
            $pattern = $row[17];
            $employee = $this->employees[$nik];

            if ($nik === 'EMP-2024-089' && $month === 3) {
                $this->budiMarch($employee, $days);
            } elseif ($nik === 'EMP-2023-118' && $month === 3) {
                // Kriteria keberterimaan 2: terlambat 65 menit sekali → 1 hari (bukan 2).
                $this->writeDays($employee, $days, fn (int $i) => ['HADIR', $i === 6 ? 65 : 0]);
            } else {
                $leave = array_rand(array_flip(range(0, $days->count() - 1)), 2);
                $leaveCount = mt_rand(0, 2);
                $this->writeDays($employee, $days, function (int $i) use ($pattern, $leave, $leaveCount, $nik, $month) {
                    if ($leaveCount > 0 && $i === $leave[0]) {
                        return [mt_rand(0, 1) ? 'IZIN' : 'SAKIT', 0];
                    }
                    if ($leaveCount > 1 && $i === $leave[1]) {
                        return ['CUTI', 0];
                    }
                    if ($nik === 'EMP-2025-201' && $month === 9 && $i === 3) {
                        return ['ALPA', 0];
                    }

                    return ['HADIR', $this->lateMinutes($pattern)];
                });
            }

            if ($nik !== 'EMP-2024-089' || $month !== 3) {
                $hours = match ($pattern) {
                    'lembur' => mt_rand(15, 25),
                    'disiplin' => 0,
                    default => mt_rand(0, 8),
                };
                if ($hours > 0) {
                    OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => $days[10]->toDateString(), 'hours' => $hours, 'status' => 'APPROVED', 'notes' => 'Lembur kunjungan pasien / tutup buku']);
                }
                if ($month === 9 && $nik === 'EMP-2023-118') {
                    OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => $days[15]->toDateString(), 'hours' => 3, 'status' => 'PENDING', 'notes' => 'Belum disetujui atasan']);
                }
            }

            $isHendraTeam = $row[16] === 'EMP-2018-007';
            KpiScore::create([
                'employee_id' => $employee->id,
                'period_code' => $periodCode,
                'score' => ($nik === 'EMP-2024-089' && $month === 3) ? 92 : mt_rand(68, 97),
                'confirmed_by' => ($isHendraTeam && $month !== self::DRAFT_MONTH) ? $hendra?->id : null,
                'confirmed_at' => ($isHendraTeam && $month !== self::DRAFT_MONTH) ? $start->copy()->endOfMonth() : null,
            ]);
        }
    }

    /** Persis contoh slip: 23 hadir, 2 izin/sakit, telat 62 & 63 menit, lembur 7 jam, KPI 92. */
    private function budiMarch(Employee $employee, $days): void
    {
        $this->writeDays($employee, $days, fn (int $i) => match ($i) {
            9 => ['IZIN', 0],
            17 => ['SAKIT', 0],
            3 => ['HADIR', 62],
            11 => ['HADIR', 63],
            default => ['HADIR', 0],
        });
        OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => '2026-03-14', 'hours' => 4, 'status' => 'APPROVED', 'notes' => 'Tutup buku bulanan']);
        OvertimeRecord::create(['employee_id' => $employee->id, 'work_date' => '2026-03-21', 'hours' => 3, 'status' => 'APPROVED', 'notes' => 'Rekonsiliasi bank']);
    }

    private function writeDays(Employee $employee, $days, callable $resolver): void
    {
        $rows = [];
        foreach ($days->values() as $i => $day) {
            [$status, $late] = $resolver($i);
            $checkIn = $status === 'HADIR' ? Carbon::parse('08:00')->addMinutes($late)->format('H:i:s') : null;
            $rows[] = [
                'employee_id' => $employee->id,
                'work_date' => $day->toDateString(),
                'status' => $status,
                'scheduled_start' => '08:00:00',
                'check_in_at' => $checkIn,
                'check_out_at' => $status === 'HADIR' ? '17:00:00' : null,
                'late_minutes' => $late,
                'source' => 'RUMATKU',
                'created_at' => now(),
                'updated_at' => now(),
            ];
        }
        AttendanceLog::insert($rows);
    }

    private function lateMinutes(string $pattern): int
    {
        $roll = mt_rand(1, 100);

        return match ($pattern) {
            'disiplin' => $roll <= 4 ? mt_rand(1, 10) : 0,
            'sering_telat' => match (true) {
                $roll <= 28 => mt_rand(16, 25),
                $roll <= 40 => mt_rand(3, 12),
                default => 0,
            },
            default => match (true) {
                $roll <= 2 => mt_rand(60, 75),
                $roll <= 7 => mt_rand(15, 35),
                $roll <= 17 => mt_rand(1, 12),
                default => 0,
            },
        };
    }

    private function email(string $name): string
    {
        return strtolower(str_replace(' ', '.', $name)).'@rosy.test';
    }
}
