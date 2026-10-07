<?php

namespace App\Providers;

use App\Models\Payslip;
use App\Models\User;
use App\Services\Payroll\Contracts\PayrollDataSource;
use App\Services\Payroll\DatabasePayrollDataSource;
use App\Services\Payroll\PayrollSettings;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        // Ganti dengan adapter API Rumatku/ROSY saat integrasi produksi.
        $this->app->bind(PayrollDataSource::class, DatabasePayrollDataSource::class);

        // Dibaca ulang per request/job supaya perubahan Pengaturan langsung berlaku di queue worker.
        $this->app->scoped(PayrollSettings::class);
    }

    public function boot(): void
    {
        // Kriteria keberterimaan 4: menu & aksi edit payroll hanya untuk MANAGER_HRD.
        Gate::define('manage-payroll', fn (User $user) => $user->isManagerHrd());

        Gate::define('view-attendance-deductions', fn (User $user) => $user->hasRole(User::ROLE_MANAGER_HRD, User::ROLE_STAFF_HRD));

        Gate::define('confirm-team-kpi', fn (User $user) => $user->hasRole(User::ROLE_ATASAN_DIVISI, User::ROLE_MANAGER_HRD));

        // Karyawan hanya boleh mengakses slip miliknya yang sudah published.
        Gate::define('view-own-payslip', fn (User $user, Payslip $payslip) => $user->employee_id !== null
            && $payslip->employee_id === $user->employee_id
            && $payslip->isPublished());
    }
}
