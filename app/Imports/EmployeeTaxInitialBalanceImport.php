<?php

namespace App\Imports;

use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\Payslip;
use App\Services\Payroll\Pph21TerCalculatorService;
use App\Support\Money;
use App\Support\NumberParser;
use Closure;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use InvalidArgumentException;
use Maatwebsite\Excel\Concerns\SkipsEmptyRows;
use Maatwebsite\Excel\Concerns\ToCollection;
use Maatwebsite\Excel\Concerns\WithCalculatedFormulas;
use Maatwebsite\Excel\Concerns\WithCustomCsvSettings;
use Maatwebsite\Excel\Concerns\WithStartRow;

/**
 * Impor saldo awal pajak YTD (Modul 4A). Kolom berurutan sesuai template:
 * NIK, tahun pajak, bulan cut-off, status PTKP, bruto YTD, iuran JHT+JP pekerja
 * YTD, biaya jabatan YTD, PPh 21 dibayar YTD, catatan. Baris 1 = judul kolom.
 *
 * Mode dry-run hanya memvalidasi; mode simpan memakai updateOrCreate per
 * (employee_id, tax_year) untuk baris yang lolos validasi.
 */
class EmployeeTaxInitialBalanceImport implements SkipsEmptyRows, ToCollection, WithCalculatedFormulas, WithCustomCsvSettings, WithStartRow
{
    public const COLUMNS = [
        'nik', 'tax_year', 'cutoff_month', 'ptkp_status', 'gross_income_ytd',
        'employee_jht_jp_ytd', 'biaya_jabatan_ytd', 'pph21_paid_ytd', 'notes',
    ];

    public int $total = 0;

    public int $saved = 0;

    /** @var list<array<string, mixed>> */
    public array $valid = [];

    /** @var list<array{row: int, nik: string, messages: list<string>}> */
    public array $errors = [];

    /** @var list<array{row: int, nik: string, message: string}> */
    public array $warnings = [];

    public function __construct(
        private readonly bool $dryRun = true,
        private readonly string $delimiter = ',',
        private readonly ?Closure $onStart = null,
        private readonly ?Closure $onRow = null,
    ) {}

    public function startRow(): int
    {
        return 2;
    }

    public function getCsvSettings(): array
    {
        return ['delimiter' => $this->delimiter, 'input_encoding' => 'UTF-8'];
    }

    public function collection(Collection $collection): void
    {
        $nikToId = Employee::query()->pluck('id', 'nik');
        $systemMonths = $this->systemMonths();
        $seen = [];
        $this->total = $collection->count();
        if ($this->onStart) {
            ($this->onStart)($this->total);
        }

        foreach ($collection->values() as $index => $row) {
            $rowNumber = $index + $this->startRow();
            $cells = array_pad(array_values($row->toArray()), count(self::COLUMNS), null);
            $data = array_combine(self::COLUMNS, array_slice($cells, 0, count(self::COLUMNS)));
            $nik = trim((string) $data['nik']);

            [$clean, $messages] = $this->validateRow($data, $nikToId->all());

            $key = $nik.'|'.($clean['tax_year'] ?? '');
            if (! $messages && isset($seen[$key])) {
                $messages[] = "Duplikat NIK {$nik} untuk tahun {$clean['tax_year']} (sudah ada di baris {$seen[$key]}).";
            }

            // Saldo awal tidak boleh mencakup bulan yang sudah diproses sistem baru (bruto terhitung dua kali).
            if (! $messages) {
                $processed = $systemMonths[$clean['employee_id'].'|'.$clean['tax_year']] ?? [];
                $overlap = array_values(array_filter($processed, fn (int $m) => $m <= $clean['cutoff_month']));
                if ($overlap) {
                    $maxCutoff = min($processed) - 1;
                    $messages[] = 'Bulan '.implode(', ', $overlap).' tahun '.$clean['tax_year'].' sudah diproses sistem baru; '
                        .($maxCutoff > 0 ? "cut-off saldo awal maksimal {$maxCutoff}." : 'saldo awal tidak diperlukan karena sistem sudah memproses sejak Januari.');
                }
            }

            if ($messages) {
                $this->errors[] = ['row' => $rowNumber, 'nik' => $nik, 'messages' => $messages];
            } else {
                $seen[$key] = $rowNumber;
                $this->valid[] = $clean + ['row' => $rowNumber, 'nik' => $nik];
                $cap = 500_000 * $clean['cutoff_month'];
                if ($clean['biaya_jabatan_ytd'] > $cap) {
                    $this->warnings[] = ['row' => $rowNumber, 'nik' => $nik, 'message' => 'Biaya jabatan YTD melebihi plafon Rp500.000 × '.$clean['cutoff_month'].' bulan.'];
                }
            }

            if ($this->onRow) {
                ($this->onRow)($rowNumber);
            }
        }

        if (! $this->dryRun) {
            $this->persist();
        }
    }

    /**
     * @param  array<string, mixed>  $data
     * @param  array<string, int>  $nikToId
     * @return array{0: array<string, mixed>, 1: list<string>}
     */
    public function validateRow(array $data, array $nikToId): array
    {
        $messages = [];
        $clean = [];

        $nik = trim((string) $data['nik']);
        if ($nik === '') {
            $messages[] = 'NIK wajib diisi.';
        } elseif (! isset($nikToId[$nik])) {
            $messages[] = "NIK {$nik} tidak ditemukan di master karyawan ROSY.";
        } else {
            $clean['employee_id'] = $nikToId[$nik];
        }

        $year = NumberParser::parse($data['tax_year']);
        if ($year === null || floor($year) != $year || $year < 2000 || $year > (int) date('Y') + 1) {
            $messages[] = 'Tahun pajak harus format YYYY (2000–'.((int) date('Y') + 1).').';
        } else {
            $clean['tax_year'] = (int) $year;
        }

        $month = NumberParser::parse($data['cutoff_month']);
        if ($month === null || floor($month) != $month || $month < 1 || $month > 11) {
            $messages[] = 'Bulan cut-off harus bilangan bulat 1 s/d 11.';
        } else {
            $clean['cutoff_month'] = (int) $month;
        }

        try {
            $clean['ptkp_status'] = Pph21TerCalculatorService::normalizeStatus((string) $data['ptkp_status']);
        } catch (InvalidArgumentException) {
            $messages[] = 'Status PTKP harus salah satu dari: '.implode(', ', Employee::PTKP_STATUSES).'.';
        }

        foreach (['gross_income_ytd' => 'Bruto YTD', 'employee_jht_jp_ytd' => 'Iuran JHT & JP YTD',
            'biaya_jabatan_ytd' => 'Biaya jabatan YTD', 'pph21_paid_ytd' => 'PPh 21 dibayar YTD'] as $field => $label) {
            $value = NumberParser::parse($data[$field]);
            if ($value === null || $value < 0) {
                $messages[] = "{$label} harus angka >= 0.";
            } else {
                $clean[$field] = Money::round($value);
            }
        }

        $notes = trim((string) ($data['notes'] ?? ''));
        if (mb_strlen($notes) > 1000) {
            $messages[] = 'Catatan maksimal 1000 karakter.';
        }
        $clean['notes'] = $notes === '' ? null : $notes;

        return [$clean, $messages];
    }

    private function persist(): void
    {
        DB::transaction(function () {
            foreach ($this->valid as $row) {
                EmployeeTaxInitialBalance::updateOrCreate(
                    ['employee_id' => $row['employee_id'], 'tax_year' => $row['tax_year']],
                    collect($row)->only([
                        'cutoff_month', 'ptkp_status', 'gross_income_ytd', 'employee_jht_jp_ytd',
                        'biaya_jabatan_ytd', 'pph21_paid_ytd', 'notes',
                    ])->all(),
                );
                $this->saved++;
            }
        });
    }

    /** @return array<string, list<int>> "employee_id|tahun" => bulan yang sudah punya slip sistem */
    private function systemMonths(): array
    {
        return Payslip::query()
            ->join('payroll_periods', 'payroll_periods.id', '=', 'payslips.payroll_period_id')
            ->selectRaw('payslips.employee_id, YEAR(payroll_periods.start_date) as y, MONTH(payroll_periods.start_date) as m')
            ->get()
            ->groupBy(fn ($r) => $r->employee_id.'|'.$r->y)
            ->map(fn ($rows) => $rows->pluck('m')->map(fn ($m) => (int) $m)->sort()->values()->all())
            ->all();
    }

    /** Tebak pemisah CSV dari baris pertama (Excel versi Indonesia sering memakai titik koma). */
    public static function detectDelimiter(string $path): string
    {
        $handle = @fopen($path, 'rb');
        $first = $handle ? (string) fgets($handle) : '';
        if ($handle) {
            fclose($handle);
        }

        return substr_count($first, ';') > substr_count($first, ',') ? ';' : ',';
    }
}
