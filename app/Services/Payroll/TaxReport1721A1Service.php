<?php

namespace App\Services\Payroll;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\Payslip;
use App\Support\Money;
use App\Support\Tanggal;
use Barryvdh\DomPDF\Facade\Pdf;
use DomainException;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;

/**
 * Bukti pemotongan PPh 21 Formulir 1721-A1 (Modul 5B), dihitung dari saldo awal
 * YTD + seluruh slip final setahun. Dokumen pendamping internal: bukti potong
 * resmi tetap diterbitkan lewat Coretax DJP.
 */
class TaxReport1721A1Service
{
    public const LINES = [
        1 => 'Gaji/Pensiun atau THT/JHT',
        2 => 'Tunjangan PPh',
        3 => 'Tunjangan Lainnya, Uang Lembur dan Sebagainya',
        4 => 'Honorarium dan Imbalan Lain Sejenisnya',
        5 => 'Premi Asuransi yang Dibayar Pemberi Kerja',
        6 => 'Penerimaan dalam Bentuk Natura dan Kenikmatan Lainnya yang Dikenakan Pemotongan PPh Pasal 21',
        7 => 'Tantiem, Bonus, Gratifikasi, Jasa Produksi dan THR',
        8 => 'Jumlah Penghasilan Bruto (1 s.d. 7)',
        9 => 'Biaya Jabatan/Biaya Pensiun',
        10 => 'Iuran Terkait Program Pensiun/JHT/THT',
        11 => 'Zakat/Sumbangan Keagamaan yang Bersifat Wajib yang Dibayarkan melalui Pemberi Kerja',
        12 => 'Jumlah Pengurangan (9 s.d. 11)',
        13 => 'Jumlah Penghasilan Neto (8 − 12)',
        14 => 'Penghasilan Neto dari Pemotongan Sebelumnya',
        15 => 'Jumlah Penghasilan Neto untuk Penghitungan PPh Pasal 21 (Setahun/Disetahunkan)',
        16 => 'Penghasilan Tidak Kena Pajak (PTKP)',
        17 => 'Penghasilan Kena Pajak Setahun/Disetahunkan (15 − 16)',
        18 => 'PPh Pasal 21 atas Penghasilan Kena Pajak Setahun/Disetahunkan',
        19 => 'PPh Pasal 21 yang Telah Dipotong pada Bukti Pemotongan Sebelumnya',
        20 => 'PPh Pasal 21 Terutang (18 − 19)',
        21 => 'PPh Pasal 21 yang Telah Dipotong Masa Pajak Januari s.d. Sebelum Masa Pajak Terakhir',
        22 => 'PPh Pasal 21 Kurang (Lebih) Dipotong pada Masa Pajak Terakhir (20 − 21)',
    ];

    public function __construct(
        private readonly Pph21CalculatorService $pph21,
        private readonly Pph21TerCalculatorService $ter,
        private readonly PayrollSettings $settings,
        private readonly PdfEncryptor $encryptor,
    ) {}

    /** @return Collection<int, Employee> karyawan yang punya data pajak pada tahun itu */
    public function employeesWithData(int $taxYear): Collection
    {
        return Employee::query()
            ->where(fn ($q) => $q
                ->whereHas('payslips', fn ($p) => $p->finalized()->whereHas('period', fn ($r) => $r->whereYear('start_date', $taxYear)))
                ->orWhereHas('taxInitialBalances', fn ($b) => $b->where('tax_year', $taxYear)))
            ->orderBy('full_name')
            ->get();
    }

    /**
     * @return array<string, mixed>
     */
    public function generateAnnualReport(Employee $employee, int $taxYear): array
    {
        /** @var Collection<int, Payslip> $slips */
        $slips = Payslip::query()
            ->finalized()
            ->where('employee_id', $employee->id)
            ->whereHas('period', fn ($q) => $q->whereYear('start_date', $taxYear))
            ->with('period')
            ->get()
            ->sortBy(fn (Payslip $s) => $s->period->start_date)
            ->values();

        $init = EmployeeTaxInitialBalance::query()
            ->where('employee_id', $employee->id)
            ->where('tax_year', $taxYear)
            ->first();

        if ($slips->isEmpty() && ! $init) {
            throw new DomainException("Tidak ada data penghasilan {$employee->full_name} pada tahun pajak {$taxYear}.");
        }

        $months = [];
        $overlap = [];
        if ($init) {
            for ($m = $this->pph21->firstWorkingMonth($employee, $taxYear); $m <= $init->cutoff_month; $m++) {
                $months[$m] = true;
            }
        }
        foreach ($slips as $slip) {
            if ($init && $slip->period->month() <= $init->cutoff_month) {
                $overlap[] = Tanggal::BULAN[$slip->period->month()];
            }
            $months[$slip->period->month()] = true;
        }
        ksort($months);
        $monthCount = count($months);

        $finalSlip = $slips->first(fn (Payslip $s) => $this->pph21->isFinalTaxPeriod($s->period, $employee));

        $sum = fn (callable $f) => (int) $slips->sum($f);
        $breakdown = fn (Payslip $s, string $key) => (int) (($s->bpjs_breakdown ?? [])[$key] ?? 0);

        $l = array_fill(1, 22, 0);
        $l[1] = ($init?->gross_income_ytd ?? 0) + $sum(fn (Payslip $s) => $s->basic_salary);
        $l[3] = $sum(fn (Payslip $s) => $s->position_allowance + $s->attendance_allowance + $s->overtime_pay
            + $breakdown($s, 'jht_company') + $breakdown($s, 'jp_company'));
        $l[5] = $sum(fn (Payslip $s) => $breakdown($s, 'kes_company') + $breakdown($s, 'jkk') + $breakdown($s, 'jkm'));
        $l[7] = $sum(fn (Payslip $s) => $s->kpi_incentive + $s->additional_bonus);
        $l[8] = $l[1] + $l[2] + $l[3] + $l[4] + $l[5] + $l[6] + $l[7];

        $cap = min(Pph21CalculatorService::BIAYA_JABATAN_MAX_YEARLY, Pph21CalculatorService::BIAYA_JABATAN_MAX_MONTHLY * $monthCount);
        $l[9] = min(Money::pctBp($l[8], Pph21CalculatorService::BIAYA_JABATAN_BP), $cap);
        $l[10] = ($init?->employee_jht_jp_ytd ?? 0) + $sum(fn (Payslip $s) => $s->employee_jht_jp);
        $l[12] = $l[9] + $l[10] + $l[11];
        $l[13] = $l[8] - $l[12];
        $l[15] = $l[13] + $l[14];

        $ptkpStatus = $this->pph21->taxYearPtkpStatus($employee, $taxYear);
        $l[16] = $this->ter->ptkp($ptkpStatus);
        $l[17] = intdiv(max(0, $l[15] - $l[16]), 1000) * 1000;
        $l[18] = $this->pph21->annualTax($l[17]);
        $l[20] = $l[18] - $l[19];
        $l[21] = ($init?->pph21_paid_ytd ?? 0)
            + $sum(fn (Payslip $s) => ($finalSlip && $s->is($finalSlip)) ? 0 : $s->pph21_amount);
        $l[22] = $l[20] - $l[21];

        $warnings = [];
        if ($overlap) {
            $warnings[] = 'Saldo awal YTD (s/d '.Tanggal::BULAN[$init->cutoff_month].') tumpang tindih dengan slip sistem bulan '
                .implode(', ', $overlap).': bruto terhitung dua kali. Perbaiki saldo awal.';
        }
        $systemGross = ($init?->gross_income_ytd ?? 0) + $sum(fn (Payslip $s) => $s->gross_earnings);
        if ($systemGross !== $l[8]) {
            $warnings[] = 'Jumlah bruto per komponen ('.Money::rupiah($l[8]).') berbeda dengan total bruto slip ('.Money::rupiah($systemGross).').';
        }
        if ($finalSlip && $finalSlip->pph21_amount !== $l[22]) {
            $warnings[] = 'PPh 21 masa terakhir di slip ('.Money::rupiah($finalSlip->pph21_amount).') berbeda dengan baris 22 ('
                .Money::rupiah($l[22]).'). Periksa perubahan data setelah slip masa terakhir dikunci.';
        }
        if (! $finalSlip) {
            $warnings[] = 'Masa pajak terakhir (Desember / bulan berhenti bekerja) belum diproses: dokumen ini SEMENTARA.';
        }

        $firstMonth = array_key_first($months);
        $lastMonth = array_key_last($months);

        return [
            'tax_year' => $taxYear,
            'is_final' => (bool) $finalSlip,
            'number' => sprintf('1.1-%02d.%s-%07d', $lastMonth, substr((string) $taxYear, -2), $employee->id),
            'period_from' => $firstMonth,
            'period_to' => $lastMonth,
            'months_worked' => $monthCount,
            'employer' => [
                'npwp' => $this->settings->get('COMPANY_NPWP'),
                'name' => $this->settings->get('COMPANY_NAME'),
                'address' => $this->settings->get('COMPANY_ADDRESS'),
                'signer' => $this->settings->get('HR_MANAGER_NAME'),
                'signer_title' => $this->settings->get('HR_MANAGER_TITLE'),
            ],
            'employee' => [
                'nik' => $employee->nik,
                'npwp' => $employee->npwp,
                'national_id' => $employee->national_id,
                'name' => $employee->full_name,
                'address' => $employee->address,
                'gender' => $employee->gender === 'P' ? 'Perempuan' : 'Laki-laki',
                'ptkp_status' => $ptkpStatus,
                'position' => $employee->position,
            ],
            'lines' => $l,
            'source' => [
                'initial_balance' => $init ? [
                    'cutoff_month' => $init->cutoff_month,
                    'gross' => $init->gross_income_ytd,
                    'pph21' => $init->pph21_paid_ytd,
                ] : null,
                'payslip_count' => $slips->count(),
            ],
            'warnings' => $warnings,
        ];
    }

    /** PDF tanpa enkripsi (unduhan Manager HRD). */
    public function renderPdf(array $report): string
    {
        $html = view('pdf.form_1721_a1', [
            'r' => $report,
            'lineLabels' => self::LINES,
            'printedAt' => Tanggal::panjang(Carbon::now()),
            'monthNames' => Tanggal::BULAN,
        ])->render();

        return Pdf::loadHTML($html)->setPaper('a4', 'portrait')
            ->setOption(['defaultFont' => 'Roboto', 'isRemoteEnabled' => false])
            ->output();
    }

    /**
     * PDF terenkripsi DDMMYY untuk diunduh karyawan (Rumatku). Hanya dokumen final:
     * versi sementara di tengah tahun menampilkan proyeksi lebih/kurang potong
     * yang belum bermakna untuk SPT.
     */
    public function encryptedPdf(Employee $employee, int $taxYear): string
    {
        $report = $this->generateAnnualReport($employee, $taxYear);
        if (! $report['is_final']) {
            throw new DomainException("Bukti potong tahun {$taxYear} belum final; terbit setelah masa pajak terakhir (Desember / bulan berhenti bekerja) diproses.");
        }

        return $this->encryptor->encrypt(
            $this->renderPdf($report),
            $employee->pdfPassword(),
            ['title' => 'Bukti Potong PPh 21 (1721-A1) Tahun '.$taxYear, 'author' => 'HRIS ROSY', 'subject' => 'Dokumen Rahasia'],
        );
    }

    public function filename(Employee $employee, int $taxYear): string
    {
        return sprintf('1721-A1_%d_%s.pdf', $taxYear, $employee->nik);
    }
}
