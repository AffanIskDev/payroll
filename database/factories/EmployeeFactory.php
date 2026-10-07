<?php

namespace Database\Factories;

use App\Models\Employee;
use App\Models\EmployeeSalaryProfile;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Employee>
 */
class EmployeeFactory extends Factory
{
    protected $model = Employee::class;

    public function definition(): array
    {
        return [
            'nik' => 'EMP-'.fake()->unique()->numerify('####-###'),
            'full_name' => fake()->name(),
            'email' => fake()->unique()->safeEmail(),
            'birth_date' => fake()->dateTimeBetween('-50 years', '-21 years')->format('Y-m-d'),
            'gender' => fake()->randomElement(['L', 'P']),
            'ptkp_status' => 'TK/0',
            'department' => 'Keuangan',
            'position' => 'Staff',
            'employment_status' => 'PKWTT (Tetap)',
            'is_management' => false,
            'join_date' => '2024-01-02',
            'is_active' => true,
        ];
    }

    /**
     * @param  array<string, mixed>  $profile
     */
    public function withProfile(array $profile = []): static
    {
        return $this->afterCreating(function (Employee $employee) use ($profile) {
            EmployeeSalaryProfile::create($profile + [
                'employee_id' => $employee->id,
                'basic_salary' => 6_000_000,
                'position_allowance' => 0,
                'monthly_attendance_allowance' => 0,
                'overtime_hourly_rate' => 0,
                'jkk_rate' => 0.0024,
                'bank_name' => 'BCA',
                'bank_account_number' => fake()->numerify('##########'),
                'bank_account_name' => mb_strtoupper($employee->full_name),
            ]);
        });
    }
}
