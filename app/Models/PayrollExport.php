<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Log setiap file transfer bank yang diunduh (jejak audit). */
class PayrollExport extends Model
{
    protected $fillable = [
        'payroll_period_id', 'user_id', 'bank', 'debit_account', 'effective_date', 'file_name',
        'row_count', 'total_amount',
    ];

    protected function casts(): array
    {
        return [
            'effective_date' => 'date',
            'row_count' => 'integer',
            'total_amount' => Rupiah::class,
        ];
    }

    public function period(): BelongsTo
    {
        return $this->belongsTo(PayrollPeriod::class, 'payroll_period_id');
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
