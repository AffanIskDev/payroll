<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Payslip extends Model
{
    public const STATUS_DRAFT = 'draft';

    public const STATUS_LOCKED = 'locked';

    public const STATUS_PUBLISHED = 'published';

    public const STATUS_LABELS = [
        self::STATUS_DRAFT => 'Draft - Menunggu Approval',
        self::STATUS_LOCKED => 'Terkunci - Memproses PDF',
        self::STATUS_PUBLISHED => 'Published',
    ];

    /** Kolom yang boleh diubah Manager HRD di workbench (PRD langkah 4). */
    public const OVERRIDABLE = [
        'overtime_pay' => 'Uang Lembur',
        'kpi_incentive' => 'Insentif KPI / Kinerja',
        'additional_bonus' => 'Bonus Tambahan',
        'late_penalty_amount' => 'Potongan Keterlambatan',
        'other_deductions' => 'Potongan Kasbon / Lain-lain',
    ];

    protected $guarded = ['id'];

    protected function casts(): array
    {
        $money = array_fill_keys([
            'basic_salary', 'position_allowance', 'attendance_allowance', 'bpjs_kes_base_salary',
            'bpjs_tk_base_salary', 'bpjs_jp_base_salary', 'late_penalty_amount', 'overtime_rate',
            'overtime_pay', 'kpi_incentive', 'additional_bonus', 'tunjangan_bpjs_kes', 'tunjangan_bpjs_tk',
            'gross_earnings', 'iuran_bpjs_kes_total', 'iuran_bpjs_tk_total', 'employee_jht_jp',
            'pph21_amount', 'other_deductions', 'total_deductions', 'take_home_pay',
        ], Rupiah::class);

        return $money + [
            'ter_rate' => 'float',
            'jkk_rate' => 'decimal:4',
            'overtime_hours' => 'float',
            'kpi_score' => 'float',
            'bpjs_breakdown' => 'array',
            'pph21_breakdown' => 'array',
            'system_values' => 'array',
            'overrides' => 'array',
            'is_manually_adjusted' => 'boolean',
            'pdf_generated_at' => 'datetime',
            'locked_at' => 'datetime',
            'published_at' => 'datetime',
            'bsi_exported_at' => 'datetime',
        ];
    }

    public function period(): BelongsTo
    {
        return $this->belongsTo(PayrollPeriod::class, 'payroll_period_id');
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }

    public function adjustments(): HasMany
    {
        return $this->hasMany(PayslipAdjustment::class)->latest('id');
    }

    public function lockedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'locked_by');
    }

    /** Slip yang sudah boleh dilihat karyawan di Rumatku. */
    public function scopePublished(Builder $query): Builder
    {
        return $query->where($query->qualifyColumn('status'), self::STATUS_PUBLISHED);
    }

    /** Slip final (sudah disetujui), dipakai untuk transfer & laporan pajak. */
    public function scopeFinalized(Builder $query): Builder
    {
        return $query->whereIn($query->qualifyColumn('status'), [self::STATUS_LOCKED, self::STATUS_PUBLISHED]);
    }

    public function isDraft(): bool
    {
        return $this->status === self::STATUS_DRAFT;
    }

    public function isPublished(): bool
    {
        return $this->status === self::STATUS_PUBLISHED;
    }

    public function statusLabel(): string
    {
        return self::STATUS_LABELS[$this->status] ?? $this->status;
    }

    public function totalEarnings(): int
    {
        return $this->gross_earnings;
    }
}
