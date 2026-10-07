<?php

namespace App\Http\Controllers\Ess;

use App\Http\Controllers\Controller;
use App\Services\Payroll\TaxReport1721A1Service;
use DomainException;
use Illuminate\Http\Request;
use Illuminate\View\View;
use Symfony\Component\HttpFoundation\Response;

class MyTaxDocumentController extends Controller
{
    public function index(Request $request, TaxReport1721A1Service $service): View
    {
        $employee = $request->user()->employee;
        abort_unless($employee, 403, 'Akun ini tidak terhubung ke data karyawan.');

        $years = $employee->payslips()->published()->join('payroll_periods', 'payroll_periods.id', '=', 'payslips.payroll_period_id')
            ->selectRaw('DISTINCT YEAR(payroll_periods.start_date) as y')->pluck('y')
            ->merge($employee->taxInitialBalances()->pluck('tax_year'))
            ->map(fn ($y) => (int) $y)->unique()->sortDesc()->values();

        $reports = $years->map(function (int $year) use ($service, $employee) {
            try {
                return ['year' => $year, 'report' => $service->generateAnnualReport($employee, $year)];
            } catch (DomainException) {
                return null;
            }
        })->filter();

        $documents = $reports->filter(fn (array $d) => $d['report']['is_final'])->values();
        $pendingYears = $reports->reject(fn (array $d) => $d['report']['is_final'])->pluck('year')->values();

        return view('my.tax-documents', compact('documents', 'pendingYears', 'employee'));
    }

    public function download(Request $request, int $year, TaxReport1721A1Service $service): Response
    {
        $employee = $request->user()->employee;
        abort_unless($employee, 403);

        try {
            $pdf = $service->encryptedPdf($employee, $year);
        } catch (DomainException $e) {
            abort(404, $e->getMessage());
        }

        return response($pdf, 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.$service->filename($employee, $year).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }
}
