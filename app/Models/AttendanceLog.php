<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Presensi harian dari Rumatku. */
class AttendanceLog extends Model
{
    protected $fillable = [
        'employee_id', 'work_date', 'status', 'scheduled_start', 'check_in_at', 'check_out_at',
        'late_minutes', 'source',
    ];

    protected function casts(): array
    {
        return [
            'work_date' => 'date',
            'late_minutes' => 'integer',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }
}
