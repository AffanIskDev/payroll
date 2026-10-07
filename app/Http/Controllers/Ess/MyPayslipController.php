<?php

namespace App\Http\Controllers\Ess;

use App\Http\Controllers\Controller;
use App\Models\Payslip;
use App\Services\Payroll\PayslipPdfService;
use App\Services\Payroll\PayslipPresenter;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Storage;
use Illuminate\View\View;
use Symfony\Component\HttpFoundation\Response;

/** Menu "Slip Gaji" versi web — perilakunya sama dengan API Rumatku. */
class MyPayslipController extends Controller
{
    public function index(Request $request): View
    {
        $user = $request->user();
        abort_unless($user->employee_id, 403, 'Akun ini tidak terhubung ke data karyawan.');

        $payslips = Payslip::query()->published()
            ->where('employee_id', $user->employee_id)
            ->with('period')
            ->orderByDesc('payroll_period_id')
            ->get();

        $notifications = $user->notifications()->latest()->limit(5)->get();

        return view('my.payslips.index', compact('payslips', 'notifications'));
    }

    public function show(Request $request, Payslip $payslip, PayslipPresenter $presenter): View
    {
        Gate::authorize('view-own-payslip', $payslip);

        $request->user()->unreadNotifications()
            ->where('data->payslip_id', $payslip->id)->update(['read_at' => now()]);

        return view('my.payslips.show', ['payslip' => $payslip, 'slip' => $presenter->present($payslip)]);
    }

    public function download(Payslip $payslip, PayslipPdfService $pdf): Response
    {
        Gate::authorize('view-own-payslip', $payslip);
        $disk = Storage::disk(config('payroll.disk'));
        abort_unless($payslip->pdf_path && $disk->exists($payslip->pdf_path), 404);

        return response($disk->get($payslip->pdf_path), 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.$pdf->downloadName($payslip).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }

    public function markNotificationsRead(Request $request): RedirectResponse
    {
        $request->user()->unreadNotifications->markAsRead();

        return back();
    }
}
