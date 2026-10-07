<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Employee extends Model
{
    use HasFactory;

    public const PTKP_STATUSES = ['TK/0', 'TK/1', 'TK/2', 'TK/3', 'K/0', 'K/1', 'K/2', 'K/3'];

    protected $fillable = [
        'nik', 'full_name', 'email', 'phone', 'birth_date', 'gender', 'ptkp_status', 'npwp',
        'national_id', 'address', 'department', 'position', 'employment_status', 'is_management',
        'supervisor_id', 'join_date', 'resign_date', 'is_active',
    ];

    protected function casts(): array
    {
        return [
            'birth_date' => 'date',
            'join_date' => 'date',
            'resign_date' => 'date',
            'is_management' => 'boolean',
            'is_active' => 'boolean',
        ];
    }

    public function salaryProfile(): HasOne
    {
        return $this->hasOne(EmployeeSalaryProfile::class);
    }

    public function user(): HasOne
    {
        return $this->hasOne(User::class);
    }

    public function payslips(): HasMany
    {
        return $this->hasMany(Payslip::class);
    }

    public function taxInitialBalances(): HasMany
    {
        return $this->hasMany(EmployeeTaxInitialBalance::class);
    }

    public function attendanceLogs(): HasMany
    {
        return $this->hasMany(AttendanceLog::class);
    }

    public function overtimeRecords(): HasMany
    {
        return $this->hasMany(OvertimeRecord::class);
    }

    public function kpiScores(): HasMany
    {
        return $this->hasMany(KpiScore::class);
    }

    public function loans(): HasMany
    {
        return $this->hasMany(EmployeeLoan::class);
    }

    public function supervisor(): BelongsTo
    {
        return $this->belongsTo(self::class, 'supervisor_id');
    }

    public function subordinates(): HasMany
    {
        return $this->hasMany(self::class, 'supervisor_id');
    }

    /**
     * Peserta batch payroll suatu periode: punya profil gaji, sudah bergabung, belum
     * resign sebelum periode dimulai, dan aktif — atau resign di dalam periode ini
     * (gaji terakhir + rekonsiliasi masa pajak terakhir tetap diproses walau sudah
     * dinonaktifkan di master).
     */
    public function scopePayrollEligibleFor(Builder $query, PayrollPeriod $period): Builder
    {
        $start = $period->start_date->toDateString();
        $end = $period->end_date->toDateString();

        return $query->whereHas('salaryProfile')
            ->whereDate('join_date', '<=', $end)
            ->where(fn (Builder $q) => $q->whereNull('resign_date')->orWhereDate('resign_date', '>=', $start))
            ->where(fn (Builder $q) => $q->where('is_active', true)->orWhereBetween('resign_date', [$start, $end]));
    }

    /** Password PDF slip: tanggal lahir 6 digit DDMMYY. */
    public function pdfPassword(): string
    {
        return $this->birth_date->format('dmy');
    }

    /** Karyawan resign di dalam periode ini → masa pajak terakhir. */
    public function resignsWithin(PayrollPeriod $period): bool
    {
        return $this->resign_date !== null
            && $this->resign_date->betweenIncluded($period->start_date, $period->end_date);
    }
}
