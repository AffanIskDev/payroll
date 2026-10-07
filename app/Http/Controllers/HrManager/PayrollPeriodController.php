<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Jobs\ProcessMonthlyPayrollJob;
use App\Models\PayrollPeriod;
use App\Models\Payslip;
use App\Services\Payroll\PayslipApprovalService;
use DomainException;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\View\View;

class PayrollPeriodController extends Controller
{
    public function index(): View
    {
        $periods = PayrollPeriod::query()
            ->withCount([
                'payslips',
                'payslips as draft_count' => fn ($q) => $q->where('status', Payslip::STATUS_DRAFT),
                'payslips as published_count' => fn ($q) => $q->where('status', Payslip::STATUS_PUBLISHED),
                'payslips as adjusted_count' => fn ($q) => $q->where('is_manually_adjusted', true),
            ])
            ->withSum('payslips as total_gross', 'gross_earnings')
            ->withSum('payslips as total_deductions', 'total_deductions')
            ->withSum('payslips as total_thp', 'take_home_pay')
            ->orderByDesc('start_date')
            ->get();

        $latest = $periods->first();
        $suggested = $latest ? $latest->start_date->copy()->addMonthNoOverflow()->format('Y-m') : now()->format('Y-m');

        return view('hr-manager.payroll.index', compact('periods', 'suggested'));
    }

    public function store(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'month' => ['required', 'date_format:Y-m'],
            'generate' => ['nullable', 'boolean'],
        ], [], ['month' => 'bulan periode']);

        $month = Carbon::createFromFormat('Y-m-d', $data['month'].'-01');
        if (PayrollPeriod::where('period_code', $month->format('Y-m'))->exists()) {
            return back()->withErrors(['month' => 'Periode '.$month->format('Y-m').' sudah ada.'])->withInput();
        }

        $period = PayrollPeriod::createForMonth($month->year, $month->month, $request->user());

        if ($request->boolean('generate')) {
            $this->queueGeneration($period);
        }

        return redirect()->route('hr-manager.payroll.show', $period)
            ->with('status', "Periode {$period->period_name} dibuat.".($request->boolean('generate') ? ' Generate draft sedang diproses di antrean.' : ''));
    }

    public function show(Request $request, PayrollPeriod $period): View
    {
        $search = trim((string) $request->query('q', ''));
        $status = $request->query('status');

        $payslips = $period->payslips()
            ->when($search !== '', fn ($q) => $q->where(fn ($w) => $w
                ->where('employee_name', 'like', "%{$search}%")
                ->orWhere('employee_nik', 'like', "%{$search}%")
                ->orWhere('department', 'like', "%{$search}%")))
            ->when(in_array($status, ['draft', 'locked', 'published', 'adjusted'], true), fn ($q) => $status === 'adjusted'
                ? $q->where('is_manually_adjusted', true)
                : $q->where('status', $status))
            ->orderBy('employee_name')
            ->get();

        $totals = $period->payslips()->selectRaw('COUNT(*) as n, SUM(gross_earnings) as gross, SUM(total_deductions) as deductions,
            SUM(pph21_amount) as pph21, SUM(take_home_pay) as thp, SUM(iuran_bpjs_kes_total + iuran_bpjs_tk_total) as bpjs')->first();

        $exports = $period->exports()->with('user:id,name')->latest()->get();

        return view('hr-manager.payroll.show', compact('period', 'payslips', 'totals', 'exports', 'search', 'status'));
    }

    public function generate(PayrollPeriod $period): RedirectResponse
    {
        if (! $period->isDraft()) {
            return back()->with('error', 'Periode sudah dikunci; slip tidak bisa digenerate ulang.');
        }
        if ($period->isGenerating()) {
            return back()->with('error', 'Generate sedang berjalan.');
        }

        $this->queueGeneration($period);

        return back()->with('status', 'Generate draft payroll masuk antrean. Halaman ini memperbarui progres otomatis.');
    }

    public function approveAll(Request $request, PayrollPeriod $period, PayslipApprovalService $approval): RedirectResponse
    {
        try {
            $result = $approval->lockAll($period, $request->user());
        } catch (DomainException $e) {
            return back()->with('error', $e->getMessage());
        }

        $response = back();
        if ($result['locked'] > 0) {
            $response->with('status', "{$result['locked']} slip di-Approve & Lock (dihitung ulang dengan data terkini). PDF ber-password sedang dibuat lalu terbit ke Rumatku.");
        } elseif (! $result['skipped']) {
            $response->with('status', 'Tidak ada slip draft yang perlu di-approve.');
        }
        if ($result['skipped']) {
            $response->with('error', count($result['skipped']).' slip tetap draft: '.collect($result['skipped'])
                ->map(fn ($reason, $name) => "{$name} — {$reason}")->implode(' • '));
        }

        return $response;
    }

    public function retryPdf(PayrollPeriod $period, PayslipApprovalService $approval): RedirectResponse
    {
        $count = $approval->retryPendingPdfs($period);

        return back()->with('status', $count > 0
            ? "{$count} slip dikirim ulang ke antrean pembuatan PDF."
            : 'Tidak ada slip yang menunggu PDF.');
    }

    public function close(Request $request, PayrollPeriod $period, PayslipApprovalService $approval): RedirectResponse
    {
        try {
            $approval->close($period, $request->user());
        } catch (DomainException $e) {
            return back()->with('error', $e->getMessage());
        }

        return back()->with('status', "Periode {$period->period_name} ditutup.");
    }

    private function queueGeneration(PayrollPeriod $period): void
    {
        $period->update(['generation_status' => 'queued', 'generation_processed' => 0, 'generation_error' => null]);
        ProcessMonthlyPayrollJob::dispatch($period->id);
    }
}
