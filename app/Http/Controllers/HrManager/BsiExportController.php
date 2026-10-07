<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Models\PayrollPeriod;
use App\Services\Payroll\BsiPayrollExportService;
use DomainException;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Symfony\Component\HttpFoundation\Response;

class BsiExportController extends Controller
{
    /** Modul 5A: POST /hr-manager/payroll/{period_id}/export-bsi */
    public function store(Request $request, PayrollPeriod $period, BsiPayrollExportService $service): Response
    {
        $data = $request->validate([
            'debit_account' => ['required', 'regex:/^[0-9\-\s]{6,30}$/'],
            'effective_date' => ['required', 'date'],
            'include_exported' => ['nullable', 'boolean'],
        ], [], ['debit_account' => 'rekening debet', 'effective_date' => 'tanggal efektif transfer']);

        try {
            $export = $service->export($period, $data['debit_account'], Carbon::parse($data['effective_date']),
                $request->user(), $request->boolean('include_exported'));
        } catch (DomainException $e) {
            return back()->with('error', $e->getMessage());
        }

        return response($export['content'], 200, [
            'Content-Type' => 'text/csv; charset=UTF-8',
            'Content-Disposition' => 'attachment; filename="'.$export['filename'].'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }
}
