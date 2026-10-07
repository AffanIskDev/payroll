<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Lembur dari Rumatku; hanya status APPROVED yang dibayar. */
class OvertimeRecord extends Model
{
    protected $fillable = ['employee_id', 'work_date', 'hours', 'status', 'notes', 'source'];

    protected function casts(): array
    {
        return [
            'work_date' => 'date',
            'hours' => 'float',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }
}
