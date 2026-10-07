<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Carbon;

/** Kasbon / pinjaman internal yang dicicil lewat potongan gaji. */
class EmployeeLoan extends Model
{
    protected $fillable = [
        'employee_id', 'description', 'installment_amount', 'start_period', 'installments_total', 'is_active',
    ];

    protected function casts(): array
    {
        return [
            'installment_amount' => Rupiah::class,
            'installments_total' => 'integer',
            'is_active' => 'boolean',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }

    /** Cicilan ke berapa pada periode ini (1-based), atau null kalau tidak berlaku. */
    public function installmentNumberFor(string $periodCode): ?int
    {
        if (! $this->is_active) {
            return null;
        }
        $start = Carbon::createFromFormat('Y-m-d', $this->start_period.'-01');
        $current = Carbon::createFromFormat('Y-m-d', $periodCode.'-01');
        $diff = ($current->year - $start->year) * 12 + ($current->month - $start->month);

        return ($diff >= 0 && $diff < $this->installments_total) ? $diff + 1 : null;
    }
}
