<?php

namespace App\Http\Controllers\Api\Employee;

use App\Http\Controllers\Controller;
use App\Models\Payslip;
use App\Services\Payroll\PayslipPdfService;
use App\Services\Payroll\PayslipPresenter;
use App\Support\Money;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\HttpFoundation\Response;

/** Modul 3B: endpoint slip gaji untuk aplikasi Rumatku (auth:sanctum, throttle:60,1). */
class PayslipApiController extends Controller
{
    /** GET /api/v1/employee/payslips — riwayat slip yang sudah terbit, terbaru dulu. */
    public function index(Request $request): JsonResponse
    {
        $employee = $request->user()->employee;
        abort_unless($employee, 403, 'Akun tidak terhubung ke data karyawan.');

        $payslips = Payslip::query()->published()
            ->where('employee_id', $employee->id)
            ->with('period')
            ->orderByDesc('payroll_period_id')
            ->get();

        return response()->json([
            'status' => 'success',
            'data' => $payslips->map(fn (Payslip $p) => [
                'id' => $p->id,
                'period_code' => $p->period->period_code,
                'period_name' => $p->period->period_name,
                'payment_date' => $p->period->payment_date->toDateString(),
                'disbursement_date' => $p->period->payment_date->toDateString(),
                'take_home_pay' => $p->take_home_pay,
                'formatted_thp' => Money::rupiah($p->take_home_pay),
                'bank_name' => $p->bank_name,
                'bank_account_number' => $p->bank_account_number,
                'is_available' => $p->pdf_path !== null,
            ])->values(),
        ]);
    }

    /** GET /api/v1/employee/payslips/{id} — rincian ringkas. */
    public function show(Request $request, int $id, PayslipPresenter $presenter): JsonResponse
    {
        $payslip = $this->authorizedPayslip($request, $id);
        $slip = $presenter->present($payslip);
        $items = fn (array $rows) => array_map(fn (array $r) => [
            'key' => $r['key'], 'label' => $r['label'], 'note' => $r['caption'], 'amount' => $r['amount'],
        ], $rows);

        return response()->json([
            'status' => 'success',
            'data' => [
                'id' => $payslip->id,
                'period_code' => $payslip->period->period_code,
                'period_name' => $payslip->period->period_name,
                'payment_date' => $payslip->period->payment_date->toDateString(),
                'employee' => [
                    'nik' => $payslip->employee_nik,
                    'name' => $payslip->employee_name,
                    'position' => $payslip->position,
                    'department' => $payslip->department,
                    'ptkp_status' => $payslip->ptkp_status,
                    'tax_label' => $presenter->taxStatusLabel($payslip),
                ],
                'attendance' => [
                    'attended_days' => $payslip->attended_days,
                    'leave_sick_days' => $payslip->leave_sick_days,
                    'overtime_hours' => $payslip->overtime_hours,
                    'late_penalty_days' => $payslip->late_penalty_days,
                ],
                'earnings' => $items($slip['earnings']),
                'deductions' => $items($slip['deductions']),
                'gross_earnings' => $payslip->gross_earnings,
                'total_deductions' => $payslip->total_deductions,
                'take_home_pay' => $payslip->take_home_pay,
                'formatted_thp' => Money::rupiah($payslip->take_home_pay),
                'terbilang' => $payslip->terbilang,
                'transfer' => [
                    'bank_name' => $payslip->bank_name,
                    'bank_account_number' => $payslip->bank_account_number,
                    'account_name' => $payslip->bank_account_name,
                ],
                'pdf' => [
                    'is_available' => $payslip->pdf_path !== null,
                    'download_url' => url("/api/v1/employee/payslips/{$payslip->id}/download"),
                    'password_hint' => 'Tanggal lahir 6 digit (DDMMYY)',
                ],
            ],
        ]);
    }

    /** GET /api/v1/employee/payslips/{id}/download — PDF tetap terenkripsi DDMMYY. */
    public function downloadPdf(Request $request, int $id, PayslipPdfService $pdf): Response
    {
        $payslip = $this->authorizedPayslip($request, $id);
        $disk = Storage::disk(config('payroll.disk'));
        abort_unless($payslip->pdf_path && $disk->exists($payslip->pdf_path), 404, 'File slip belum tersedia.');

        return response($disk->get($payslip->pdf_path), 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.$pdf->downloadName($payslip).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }

    private function authorizedPayslip(Request $request, int $id): Payslip
    {
        $employee = $request->user()->employee;
        abort_unless($employee, 403, 'Akun tidak terhubung ke data karyawan.');

        $payslip = Payslip::with('period')->find($id);
        abort_unless($payslip, 404, 'Slip tidak ditemukan.');
        abort_unless($payslip->employee_id === $employee->id, 403, 'Slip ini bukan milik Anda.');
        abort_unless($payslip->isPublished(), 404, 'Slip belum terbit.');

        return $payslip;
    }
}
