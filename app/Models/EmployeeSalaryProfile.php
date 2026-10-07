<?php

namespace App\Models;

use App\Casts\Rupiah;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class EmployeeSalaryProfile extends Model
{
    protected $fillable = [
        'employee_id', 'basic_salary', 'position_allowance', 'monthly_attendance_allowance',
        'overtime_hourly_rate', 'has_bpjs_kes', 'has_jkk', 'has_jkm', 'has_jht', 'has_jp',
        'jkk_rate', 'bank_name', 'bank_account_number', 'bank_account_name',
    ];

    protected function casts(): array
    {
        return [
            'basic_salary' => Rupiah::class,
            'position_allowance' => Rupiah::class,
            'monthly_attendance_allowance' => Rupiah::class,
            'overtime_hourly_rate' => Rupiah::class,
            'has_bpjs_kes' => 'boolean',
            'has_jkk' => 'boolean',
            'has_jkm' => 'boolean',
            'has_jht' => 'boolean',
            'has_jp' => 'boolean',
            'jkk_rate' => 'decimal:4',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }
}
