<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class EmployeeTaxInitialBalance extends Model
{
    protected $fillable = [
        'employee_id', 'tax_year', 'cutoff_month', 'ptkp_status', 'gross_income_ytd',
        'employee_jht_jp_ytd', 'biaya_jabatan_ytd', 'pph21_paid_ytd', 'notes',
    ];

    protected function casts(): array
    {
        return [
            'tax_year' => 'integer',
            'cutoff_month' => 'integer',
            'gross_income_ytd' => Rupiah::class,
            'employee_jht_jp_ytd' => Rupiah::class,
            'biaya_jabatan_ytd' => Rupiah::class,
            'pph21_paid_ytd' => Rupiah::class,
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }
}
