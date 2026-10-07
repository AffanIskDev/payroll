<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class PayslipAdjustment extends Model
{
    public const UPDATED_AT = null;

    protected $fillable = ['payslip_id', 'user_id', 'field', 'old_value', 'new_value', 'reason'];

    protected function casts(): array
    {
        return ['created_at' => 'datetime'];
    }

    public function payslip(): BelongsTo
    {
        return $this->belongsTo(Payslip::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function fieldLabel(): string
    {
        return Payslip::OVERRIDABLE[$this->field] ?? match ($this->field) {
            'status' => 'Status',
            'take_home_pay' => 'Take Home Pay (hitung ulang)',
            default => $this->field,
        };
    }
}
