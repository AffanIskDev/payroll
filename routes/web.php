<?php

use App\Http\Controllers\Auth\LoginController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\Ess\MyPayslipController;
use App\Http\Controllers\Ess\MyTaxDocumentController;
use App\Http\Controllers\HrManager\BsiExportController;
use App\Http\Controllers\HrManager\EmployeeSalaryProfileController;
use App\Http\Controllers\HrManager\PayrollPeriodController;
use App\Http\Controllers\HrManager\PayrollSettingsController;
use App\Http\Controllers\HrManager\PayrollWorkbenchController;
use App\Http\Controllers\HrManager\TaxInitialBalanceImportController;
use App\Http\Controllers\HrManager\TaxReportController;
use App\Http\Controllers\HrStaff\AttendanceDeductionController;
use App\Http\Controllers\Supervisor\TeamKpiController;
use App\Models\User;
use Illuminate\Support\Facades\Route;

Route::redirect('/', '/dashboard');

Route::middleware('guest')->group(function () {
    Route::get('/login', [LoginController::class, 'show'])->name('login');
    Route::post('/login', [LoginController::class, 'login'])->middleware('throttle:10,1');
});

Route::middleware('auth')->group(function () {
    Route::post('/logout', [LoginController::class, 'logout'])->name('logout');
    Route::get('/dashboard', DashboardController::class)->name('dashboard');

    // ESS web: cermin menu "Slip Gaji" Rumatku untuk semua karyawan yang login.
    Route::prefix('my')->name('my.')->group(function () {
        Route::get('/payslips', [MyPayslipController::class, 'index'])->name('payslips');
        Route::get('/payslips/{payslip}', [MyPayslipController::class, 'show'])->whereNumber('payslip')->name('payslips.show');
        Route::get('/payslips/{payslip}/download', [MyPayslipController::class, 'download'])->whereNumber('payslip')->name('payslips.download');
        Route::post('/notifications/read', [MyPayslipController::class, 'markNotificationsRead'])->name('notifications.read');
        Route::get('/tax-documents', [MyTaxDocumentController::class, 'index'])->name('tax-documents');
        Route::get('/tax-documents/{year}', [MyTaxDocumentController::class, 'download'])->whereNumber('year')->name('tax-documents.download');
    });

    // Modul payroll Manager HRD (kriteria keberterimaan 4).
    Route::middleware('role:'.User::ROLE_MANAGER_HRD)->prefix('hr-manager')->name('hr-manager.')->group(function () {
        Route::get('/payroll', [PayrollPeriodController::class, 'index'])->name('payroll.index');
        Route::post('/payroll', [PayrollPeriodController::class, 'store'])->name('payroll.store');

        Route::get('/payroll/import-ytd', [TaxInitialBalanceImportController::class, 'create'])->name('payroll.import-ytd');
        Route::get('/payroll/import-ytd/template', [TaxInitialBalanceImportController::class, 'template'])->name('payroll.import-ytd.template');
        Route::post('/payroll/import-ytd/validate', [TaxInitialBalanceImportController::class, 'check'])->name('payroll.import-ytd.validate');
        Route::post('/payroll/import-ytd/commit', [TaxInitialBalanceImportController::class, 'commit'])->name('payroll.import-ytd.commit');

        Route::get('/payroll/settings', [PayrollSettingsController::class, 'edit'])->name('payroll.settings');
        Route::put('/payroll/settings', [PayrollSettingsController::class, 'update'])->name('payroll.settings.update');

        Route::whereNumber(['period', 'employee'])->group(function () {
            Route::get('/payroll/{period}', [PayrollPeriodController::class, 'show'])->name('payroll.show');
            Route::post('/payroll/{period}/generate', [PayrollPeriodController::class, 'generate'])->name('payroll.generate');
            Route::post('/payroll/{period}/approve-all', [PayrollPeriodController::class, 'approveAll'])->name('payroll.approve-all');
            Route::post('/payroll/{period}/close', [PayrollPeriodController::class, 'close'])->name('payroll.close');
            Route::post('/payroll/{period}/retry-pdf', [PayrollPeriodController::class, 'retryPdf'])->name('payroll.retry-pdf');
            Route::post('/payroll/{period}/export-bsi', [BsiExportController::class, 'store'])->name('payroll.export-bsi');

            Route::get('/payroll/{period}/employee/{employee}', [PayrollWorkbenchController::class, 'show'])->name('payroll.workbench');
            Route::get('/payroll/{period}/employee/{employee}/preview-pdf', [PayrollWorkbenchController::class, 'previewPdf'])->name('payroll.preview-pdf');
            Route::get('/payroll/{period}/employee/{employee}/pdf', [PayrollWorkbenchController::class, 'downloadPdf'])->name('payroll.pdf');

            Route::get('/employees', [EmployeeSalaryProfileController::class, 'index'])->name('employees.index');
            Route::get('/employees/{employee}/salary-profile', [EmployeeSalaryProfileController::class, 'edit'])->name('employees.edit');
            Route::put('/employees/{employee}/salary-profile', [EmployeeSalaryProfileController::class, 'update'])->name('employees.update');
        });

        Route::whereNumber(['year', 'employee'])->group(function () {
            Route::get('/tax/1721-a1/{year}', [TaxReportController::class, 'index'])->name('tax.index');
            Route::get('/tax/1721-a1/{year}/zip', [TaxReportController::class, 'zip'])->name('tax.zip');
            Route::get('/tax/1721-a1/{year}/{employee}', [TaxReportController::class, 'download'])->name('tax.download');
        });
    });

    Route::middleware('role:'.User::ROLE_MANAGER_HRD.','.User::ROLE_STAFF_HRD)
        ->get('/hr-staff/attendance/{period?}', [AttendanceDeductionController::class, 'index'])
        ->whereNumber('period')->name('hr-staff.attendance');

    Route::middleware('role:'.User::ROLE_ATASAN_DIVISI.','.User::ROLE_MANAGER_HRD)->group(function () {
        Route::get('/supervisor/kpi/{period?}', [TeamKpiController::class, 'index'])->whereNumber('period')->name('supervisor.kpi');
        Route::post('/supervisor/kpi/{kpiScore}/confirm', [TeamKpiController::class, 'confirm'])->whereNumber('kpiScore')->name('supervisor.kpi.confirm');
    });
});
