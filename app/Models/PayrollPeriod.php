<?php

namespace App\Models;

use App\Support\Tanggal;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Carbon;

class PayrollPeriod extends Model
{
    public const STATUS_DRAFT = 'draft';

    public const STATUS_LOCKED = 'locked';

    public const STATUS_PUBLISHED = 'published';

    public const STATUS_CLOSED = 'closed';

    public const STATUS_LABELS = [
        self::STATUS_DRAFT => 'Draft - Menunggu Approval',
        self::STATUS_LOCKED => 'Terkunci - Memproses PDF',
        self::STATUS_PUBLISHED => 'Published - Terkirim ke Rumatku',
        self::STATUS_CLOSED => 'Ditutup',
    ];

    protected $fillable = [
        'period_code', 'period_name', 'start_date', 'end_date', 'payment_date', 'status',
        'generation_status', 'generation_total', 'generation_processed', 'generation_error',
        'generated_at', 'created_by', 'approved_by', 'approved_at', 'published_at', 'closed_at',
    ];

    protected function casts(): array
    {
        return [
            'start_date' => 'date',
            'end_date' => 'date',
            'payment_date' => 'date',
            'generated_at' => 'datetime',
            'approved_at' => 'datetime',
            'published_at' => 'datetime',
            'closed_at' => 'datetime',
            'generation_total' => 'integer',
            'generation_processed' => 'integer',
        ];
    }

    /**
     * Periode cut-off tanggal 1 s/d akhir bulan, dibayar tanggal 1 bulan
     * berikutnya (PRD 3.2).
     */
    public static function createForMonth(int $year, int $month, ?User $creator = null): self
    {
        $start = Carbon::create($year, $month, 1)->startOfDay();

        return self::create([
            'period_code' => $start->format('Y-m'),
            'period_name' => Tanggal::bulanTahun($start),
            'start_date' => $start->toDateString(),
            'end_date' => $start->copy()->endOfMonth()->toDateString(),
            'payment_date' => $start->copy()->addMonthNoOverflow()->startOfMonth()->toDateString(),
            'status' => self::STATUS_DRAFT,
            'created_by' => $creator?->id,
        ]);
    }

    public function payslips(): HasMany
    {
        return $this->hasMany(Payslip::class);
    }

    public function exports(): HasMany
    {
        return $this->hasMany(PayrollExport::class);
    }

    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function approver(): BelongsTo
    {
        return $this->belongsTo(User::class, 'approved_by');
    }

    public function year(): int
    {
        return (int) $this->start_date->format('Y');
    }

    public function month(): int
    {
        return (int) $this->start_date->format('n');
    }

    public function isDraft(): bool
    {
        return $this->status === self::STATUS_DRAFT;
    }

    public function isClosed(): bool
    {
        return $this->status === self::STATUS_CLOSED;
    }

    public function statusLabel(): string
    {
        return self::STATUS_LABELS[$this->status] ?? $this->status;
    }

    public function isGenerating(): bool
    {
        return in_array($this->generation_status, ['queued', 'running'], true);
    }

    /** "Cut-off 01-31 Mar" */
    public function cutoffLabel(): string
    {
        return 'Cut-off '.$this->start_date->format('d').'-'.$this->end_date->format('d').' '
            .Tanggal::BULAN_PENDEK[$this->month()];
    }

    /**
     * Sinkronkan status periode dari status slip-slipnya:
     * ada draft → draft; semua terkunci tapi PDF belum lengkap → locked;
     * semua published → published. Periode yang sudah ditutup tidak berubah.
     */
    public function refreshStatus(): void
    {
        if ($this->isClosed()) {
            return;
        }

        $counts = $this->payslips()->selectRaw('status, COUNT(*) as total')
            ->groupBy('status')->pluck('total', 'status');

        $total = (int) $counts->sum();
        $status = match (true) {
            $total === 0, ($counts['draft'] ?? 0) > 0 => self::STATUS_DRAFT,
            ($counts['locked'] ?? 0) > 0 => self::STATUS_LOCKED,
            default => self::STATUS_PUBLISHED,
        };

        $this->status = $status;
        if ($status === self::STATUS_PUBLISHED && $this->published_at === null) {
            $this->published_at = now();
        }
        $this->save();
    }
}
