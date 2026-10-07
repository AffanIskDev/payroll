<?php

use App\Http\Controllers\Api\AuthTokenController;
use App\Http\Controllers\Api\Employee\PayslipApiController;
use App\Http\Controllers\Api\Employee\TaxDocumentApiController;
use Illuminate\Support\Facades\Route;

/*
| Kontrak REST untuk aplikasi Rumatku (PRD bab 7, Modul 3B & 5B).
| Semua endpoint karyawan memakai auth:sanctum + throttle:60,1.
*/
Route::prefix('v1')->group(function () {
    // Penerbitan token untuk integrasi & uji coba (di produksi diganti SSO Rumatku).
    Route::post('/auth/token', [AuthTokenController::class, 'store'])->middleware('throttle:10,1');

    Route::middleware(['auth:sanctum', 'throttle:60,1'])->group(function () {
        Route::delete('/auth/token', [AuthTokenController::class, 'destroy']);

        Route::prefix('employee')->whereNumber(['id', 'year'])->group(function () {
            Route::get('/payslips', [PayslipApiController::class, 'index']);
            Route::get('/payslips/{id}', [PayslipApiController::class, 'show']);
            Route::get('/payslips/{id}/download', [PayslipApiController::class, 'downloadPdf']);
            Route::get('/tax-documents/{year}', [TaxDocumentApiController::class, 'show']);
        });
    });
});
