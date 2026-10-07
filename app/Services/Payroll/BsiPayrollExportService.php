<?php

namespace App\Services\Payroll;

use App\Models\PayrollExport;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Models\User;
use App\Support\BankDirectory;
use Carbon\CarbonInterface;
use DomainException;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * File upload Payroll / Bulk Payment BSI Corporate (Modul 5A). Hanya slip yang
 * sudah disetujui (locked/published) dengan rekening tujuan dan THP > 0.
 *
 * Idempoten: slip yang sudah masuk file ditandai (payroll_export_id,
 * bsi_exported_at) dan TIDAK ikut ekspor berikutnya, kecuali diminta ekspor ulang
 * secara eksplisit — mencegah transfer gaji ganda.
 */
class BsiPayrollExportService
{
    public const HEADERS = [
        'No', 'Rekening Debet', 'Rekening Kredit', 'Nama Penerima', 'Nominal',
        'Keterangan', 'Email', 'Jenis Transfer',
    ];

    /** Batas nominal per transaksi BI-FAST. */
    public const BI_FAST_LIMIT = 250_000_000;

    public function __construct(private readonly PayrollSettings $settings) {}

    /** Slip final dengan rekening & THP > 0; tanpa yang sudah diekspor kecuali diminta. */
    private function eligibleQuery(PayrollPeriod $period, bool $includeExported): HasMany
    {
        return $period->payslips()
            ->finalized()
            ->where('bank_account_number', '<>', '')
            ->where('take_home_pay', '>', 0)
            ->when(! $includeExported, fn ($q) => $q->whereNull('bsi_exported_at'))
            ->with('employee:id,email')
            ->orderBy('employee_name');
    }

    /** @return Collection<int, Payslip> */
    public function eligiblePayslips(PayrollPeriod $period, bool $includeExported = false): Collection
    {
        return $this->eligibleQuery($period, $includeExported)->get();
    }

    /** @return array{pending: int, pending_total: int, exported: int, drafts: int} */
    public function summary(PayrollPeriod $period): array
    {
        $pending = $this->eligiblePayslips($period);

        return [
            'pending' => $pending->count(),
            'pending_total' => (int) $pending->sum('take_home_pay'),
            'exported' => $period->payslips()->whereNotNull('bsi_exported_at')->count(),
            'drafts' => $period->payslips()->where('status', Payslip::STATUS_DRAFT)->count(),
        ];
    }

    public function generateCsv(PayrollPeriod $period, string $companyDebitAccount, ?CarbonInterface $effectiveDate = null, bool $includeExported = false): string
    {
        return $this->buildCsv($period, $this->eligiblePayslips($period, $includeExported), $companyDebitAccount);
    }

    /** @param Collection<int, Payslip> $slips */
    private function buildCsv(PayrollPeriod $period, Collection $slips, string $companyDebitAccount): string
    {
        $separator = $this->settings->get('BSI_CSV_SEPARATOR') === '|' ? '|' : ',';
        $debit = $this->digits($companyDebitAccount);

        $lines = [$this->line(self::HEADERS, $separator)];
        foreach ($slips->values() as $i => $slip) {
            $lines[] = $this->line([
                (string) ($i + 1),
                $debit,
                $this->digits($slip->bank_account_number),
                $this->text($slip->bank_account_name ?: $slip->employee_name),
                (string) $slip->take_home_pay,
                $this->text("Gaji {$period->period_name} - {$slip->employee_nik}"),
                $this->text((string) $slip->employee?->email),
                $this->transferType($slip),
            ], $separator);
        }

        return implode("\r\n", $lines)."\r\n";
    }

    /**
     * Buat file, tandai slip yang masuk file, dan catat jejak audit.
     *
     * @param  bool  $includeExported  ekspor ulang slip yang sudah pernah diekspor (mengganti file gagal unggah)
     * @return array{filename: string, content: string, rows: int, total: int}
     */
    public function export(PayrollPeriod $period, string $debitAccount, CarbonInterface $effectiveDate, User $user, bool $includeExported = false): array
    {
        if ($this->digits($debitAccount) === '') {
            throw new DomainException('Nomor rekening debet BSI wajib diisi.');
        }

        return DB::transaction(function () use ($period, $debitAccount, $effectiveDate, $user, $includeExported) {
            // Locking read: ekspor kedua yang berjalan bersamaan menunggu, lalu melihat penanda dari ekspor pertama.
            $slips = $this->eligibleQuery($period, $includeExported)->lockForUpdate()->get();

            if ($slips->isEmpty()) {
                throw new DomainException($period->payslips()->finalized()->whereNotNull('bsi_exported_at')->exists()
                    ? 'Semua slip yang sudah disetujui sudah pernah diekspor. Centang "ekspor ulang" hanya bila file sebelumnya gagal diunggah.'
                    : 'Belum ada slip yang disetujui (Approve & Lock) untuk ditransfer.');
            }

            $content = $this->buildCsv($period, $slips, $debitAccount);
            $filename = sprintf('BSI_PAYROLL_%s_%s.csv', Str::of($period->period_name)->replace(' ', '_'), now()->format('Ymd_His'));
            $total = (int) $slips->sum('take_home_pay');

            $export = PayrollExport::create([
                'payroll_period_id' => $period->id,
                'user_id' => $user->id,
                'bank' => 'BSI',
                'debit_account' => $this->digits($debitAccount),
                'effective_date' => $effectiveDate->toDateString(),
                'file_name' => $filename,
                'row_count' => $slips->count(),
                'total_amount' => $total,
            ]);

            Payslip::query()->whereKey($slips->modelKeys())->update([
                'payroll_export_id' => $export->id,
                'bsi_exported_at' => now(),
            ]);

            return ['filename' => $filename, 'content' => $content, 'rows' => $slips->count(), 'total' => $total];
        });
    }

    public function transferType(Payslip $slip): string
    {
        return match (true) {
            BankDirectory::isBsi($slip->bank_name) => 'INTERNAL BSI',
            $slip->take_home_pay <= self::BI_FAST_LIMIT => 'BI-FAST',
            default => 'SKN',
        };
    }

    /** @param list<string> $values */
    private function line(array $values, string $separator): string
    {
        return implode($separator, array_map(fn (string $v) => str_replace([$separator, '"', "\r", "\n"], ' ', $v), $values));
    }

    private function digits(string $value): string
    {
        return preg_replace('/\D+/', '', $value) ?? '';
    }

    /** ASCII polos, tanpa karakter pemicu formula spreadsheet di awal. */
    private function text(string $value): string
    {
        return ltrim(trim(Str::ascii($value)), "=+-@\t");
    }
}
