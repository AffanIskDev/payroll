<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Models\Employee;
use App\Models\EmployeeTaxInitialBalance;
use App\Models\PayrollPeriod;
use App\Services\Payroll\TaxReport1721A1Service;
use DomainException;
use Illuminate\View\View;
use Symfony\Component\HttpFoundation\BinaryFileResponse;
use Symfony\Component\HttpFoundation\Response;
use ZipArchive;

/** Modul 5B: /hr-manager/tax/1721-a1/{year}/{employee_id} (per orang atau ZIP setahun). */
class TaxReportController extends Controller
{
    public function index(int $year, TaxReport1721A1Service $service): View
    {
        $reports = $service->employeesWithData($year)->map(function (Employee $employee) use ($service, $year) {
            try {
                return ['employee' => $employee, 'report' => $service->generateAnnualReport($employee, $year), 'error' => null];
            } catch (DomainException $e) {
                return ['employee' => $employee, 'report' => null, 'error' => $e->getMessage()];
            }
        });

        $years = PayrollPeriod::query()->selectRaw('YEAR(start_date) as y')->distinct()->pluck('y')
            ->merge(EmployeeTaxInitialBalance::query()->distinct()->pluck('tax_year'))
            ->push($year)->map(fn ($y) => (int) $y)->unique()->sortDesc()->values();

        return view('hr-manager.tax.index', compact('reports', 'year', 'years'));
    }

    public function download(int $year, Employee $employee, TaxReport1721A1Service $service): Response
    {
        try {
            $pdf = $service->renderPdf($service->generateAnnualReport($employee, $year));
        } catch (DomainException $e) {
            abort(404, $e->getMessage());
        }

        return response($pdf, 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.$service->filename($employee, $year).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }

    public function zip(int $year, TaxReport1721A1Service $service): BinaryFileResponse
    {
        $employees = $service->employeesWithData($year);
        abort_if($employees->isEmpty(), 404, "Belum ada data pajak tahun {$year}.");

        $tmp = tempnam(sys_get_temp_dir(), '1721a1_');
        $zip = new ZipArchive;
        $zip->open($tmp, ZipArchive::OVERWRITE);
        foreach ($employees as $employee) {
            try {
                $zip->addFromString($service->filename($employee, $year), $service->renderPdf($service->generateAnnualReport($employee, $year)));
            } catch (DomainException) {
                continue;
            }
        }
        $zip->close();

        return response()->download($tmp, "1721-A1_{$year}_semua_karyawan.zip", ['Content-Type' => 'application/zip'])
            ->deleteFileAfterSend();
    }
}
