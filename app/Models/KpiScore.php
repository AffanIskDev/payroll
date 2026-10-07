<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Skor KPI per periode dari modul KPI ROSY. */
class KpiScore extends Model
{
    protected $fillable = [
        'employee_id', 'period_code', 'score', 'incentive_amount', 'confirmed_by', 'confirmed_at', 'source',
    ];

    protected function casts(): array
    {
        return [
            'score' => 'float',
            'incentive_amount' => Rupiah::class,
            'confirmed_at' => 'datetime',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }

    public function confirmer(): BelongsTo
    {
        return $this->belongsTo(User::class, 'confirmed_by');
    }
}
