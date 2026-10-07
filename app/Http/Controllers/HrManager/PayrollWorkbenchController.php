<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Models\Employee;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Services\Payroll\PayslipPdfService;
use Illuminate\Support\Facades\Storage;
use Illuminate\View\View;
use Symfony\Component\HttpFoundation\Response;

class PayrollWorkbenchController extends Controller
{
    /** Modul 2B: /hr-manager/payroll/{period_id}/employee/{employee_id} */
    public function show(PayrollPeriod $period, Employee $employee): View
    {
        $payslip = $this->payslip($period, $employee);

        $ids = $period->payslips()->orderBy('employee_name')->pluck('employee_id')->values();
        $position = $ids->search($employee->id);
        $prev = $position > 0 ? $ids[$position - 1] : null;
        $next = $position !== false && $position < $ids->count() - 1 ? $ids[$position + 1] : null;

        return view('hr-manager.payroll.workbench', compact('period', 'employee', 'payslip', 'prev', 'next', 'position', 'ids'));
    }

    /** Pratinjau PDF (tanpa password) untuk Manager HRD, termasuk slip yang masih draft. */
    public function previewPdf(PayrollPeriod $period, Employee $employee, PayslipPdfService $pdf): Response
    {
        $payslip = $this->payslip($period, $employee);

        return response($pdf->render($payslip, previewWatermark: $payslip->isDraft()), 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="PRATINJAU_'.$pdf->downloadName($payslip).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }

    /** File final terenkripsi persis seperti yang diterima karyawan. */
    public function downloadPdf(PayrollPeriod $period, Employee $employee, PayslipPdfService $pdf): Response
    {
        $payslip = $this->payslip($period, $employee);
        $disk = Storage::disk(config('payroll.disk'));
        abort_unless($payslip->pdf_path && $disk->exists($payslip->pdf_path), 404, 'PDF terenkripsi belum dibuat. Approve & Lock dulu.');

        return response($disk->get($payslip->pdf_path), 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'attachment; filename="'.$pdf->downloadName($payslip).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }

    private function payslip(PayrollPeriod $period, Employee $employee): Payslip
    {
        return Payslip::query()
            ->where('payroll_period_id', $period->id)
            ->where('employee_id', $employee->id)
            ->with(['period', 'employee.salaryProfile'])
            ->firstOr(fn () => abort(404, 'Slip karyawan ini belum digenerate pada periode tersebut.'));
    }
}
