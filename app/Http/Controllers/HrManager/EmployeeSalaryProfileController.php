<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Models\Employee;
use App\Models\EmployeeSalaryProfile;
use App\Services\Payroll\BpjsCalculatorService;
use App\Support\BankDirectory;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Illuminate\View\View;

/** Master gaji pokok, tunjangan, checklist BPJS & rekening (di produksi bersumber dari ROSY). */
class EmployeeSalaryProfileController extends Controller
{
    public function index(Request $request): View
    {
        $search = trim((string) $request->query('q', ''));
        $employees = Employee::query()
            ->with('salaryProfile')
            ->when($search !== '', fn ($q) => $q->where(fn ($w) => $w
                ->where('full_name', 'like', "%{$search}%")
                ->orWhere('nik', 'like', "%{$search}%")
                ->orWhere('department', 'like', "%{$search}%")))
            ->orderBy('full_name')
            ->get();

        return view('hr-manager.employees.index', compact('employees', 'search'));
    }

    public function edit(Employee $employee, BpjsCalculatorService $bpjs): View
    {
        $profile = $employee->salaryProfile ?? new EmployeeSalaryProfile([
            'jkk_rate' => 0.0024, 'has_bpjs_kes' => true, 'has_jkk' => true, 'has_jkm' => true, 'has_jht' => true, 'has_jp' => true,
        ]);
        $preview = $employee->salaryProfile ? $bpjs->calculate($profile->basic_salary, $profile) : null;

        return view('hr-manager.employees.edit', [
            'employee' => $employee,
            'profile' => $profile,
            'preview' => $preview,
            'banks' => BankDirectory::BANKS,
        ]);
    }

    public function update(Request $request, Employee $employee): RedirectResponse
    {
        $data = $request->validate([
            'basic_salary' => ['required', 'integer', 'min:0', 'max:10000000000'],
            'position_allowance' => ['required', 'integer', 'min:0', 'max:10000000000'],
            'monthly_attendance_allowance' => ['required', 'integer', 'min:0', 'max:10000000000'],
            'overtime_hourly_rate' => ['required', 'integer', 'min:0', 'max:100000000'],
            'jkk_rate' => ['required', Rule::in(['0.0024', '0.0054', '0.0089', '0.0127', '0.0174'])],
            'bank_name' => ['required', Rule::in(array_keys(BankDirectory::BANKS))],
            'bank_account_number' => ['required', 'regex:/^[0-9]{6,30}$/'],
            'bank_account_name' => ['required', 'string', 'max:100'],
            'ptkp_status' => ['required', Rule::in(Employee::PTKP_STATUSES)],
        ], [], [
            'basic_salary' => 'gaji pokok',
            'monthly_attendance_allowance' => 'tunjangan kehadiran',
            'jkk_rate' => 'tarif JKK',
            'bank_account_number' => 'nomor rekening',
        ]);

        foreach (['has_bpjs_kes', 'has_jkk', 'has_jkm', 'has_jht', 'has_jp'] as $flag) {
            $data[$flag] = $request->boolean($flag);
        }

        $employee->update(['ptkp_status' => $data['ptkp_status']]);
        unset($data['ptkp_status']);
        $data['bank_account_name'] = mb_strtoupper($data['bank_account_name']);

        EmployeeSalaryProfile::updateOrCreate(['employee_id' => $employee->id], $data);

        return redirect()->route('hr-manager.employees.index')
            ->with('status', "Profil gaji {$employee->full_name} disimpan. Generate ulang slip draft agar perubahan terhitung.");
    }
}
