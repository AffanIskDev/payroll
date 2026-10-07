<?php

namespace App\Models;

use Database\Factories\UserFactory;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Laravel\Sanctum\HasApiTokens;

class User extends Authenticatable
{
    /** @use HasFactory<UserFactory> */
    use HasApiTokens, HasFactory, Notifiable;

    public const ROLE_MANAGER_HRD = 'MANAGER_HRD';

    public const ROLE_STAFF_HRD = 'STAFF_HRD';

    public const ROLE_ATASAN_DIVISI = 'ATASAN_DIVISI';

    public const ROLE_KARYAWAN = 'KARYAWAN';

    public const ROLES = [
        self::ROLE_MANAGER_HRD => 'Manager HRD',
        self::ROLE_STAFF_HRD => 'Staff HRD',
        self::ROLE_ATASAN_DIVISI => 'Atasan Divisi',
        self::ROLE_KARYAWAN => 'Karyawan',
    ];

    protected $fillable = [
        'name',
        'email',
        'password',
        'role',
        'employee_id',
    ];

    protected $hidden = [
        'password',
        'remember_token',
    ];

    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',
        ];
    }

    public function employee(): BelongsTo
    {
        return $this->belongsTo(Employee::class);
    }

    public function hasRole(string ...$roles): bool
    {
        return in_array($this->role, $roles, true);
    }

    public function isManagerHrd(): bool
    {
        return $this->role === self::ROLE_MANAGER_HRD;
    }

    public function roleLabel(): string
    {
        return self::ROLES[$this->role] ?? $this->role;
    }

    /** Halaman awal setelah login, sesuai peran. */
    public function homeRoute(): string
    {
        return match ($this->role) {
            self::ROLE_MANAGER_HRD => 'hr-manager.payroll.index',
            self::ROLE_STAFF_HRD => 'hr-staff.attendance',
            self::ROLE_ATASAN_DIVISI => 'supervisor.kpi',
            default => 'my.payslips',
        };
    }
}
