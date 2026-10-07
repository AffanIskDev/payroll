<?php

namespace App\Http\Controllers\Supervisor;

use App\Http\Controllers\Controller;
use App\Models\Employee;
use App\Models\KpiScore;
use App\Models\PayrollPeriod;
use App\Services\Payroll\KpiIncentiveResolver;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

/** Atasan Divisi mengonfirmasi skor KPI tim sebelum masuk payroll (PRD bab 2, opsional). */
class TeamKpiController extends Controller
{
    public function index(Request $request, KpiIncentiveResolver $resolver, ?PayrollPeriod $period = null): View
    {
        $periods = PayrollPeriod::query()->orderByDesc('start_date')->get(['id', 'period_code', 'period_name', 'status']);
        $period ??= $periods->first();
        $user = $request->user();

        // where('supervisor_id', null) akan menjadi whereNull dan mencakup semua karyawan puncak.
        $teamIds = match (true) {
            $user->isManagerHrd() => Employee::query()->pluck('id'),
            $user->employee_id === null => collect(),
            default => Employee::query()->where('supervisor_id', $user->employee_id)->pluck('id'),
        };

        $scores = $period
            ? KpiScore::query()->with(['employee:id,nik,full_name,position,department', 'confirmer:id,name'])
                ->where('period_code', $period->period_code)
                ->whereIn('employee_id', $teamIds)
                ->get()
                ->sortBy('employee.full_name')
                ->map(fn (KpiScore $s) => [
                    'model' => $s,
                    'incentive' => $resolver->resolve(['score' => $s->score, 'incentive_amount' => $s->incentive_amount]),
                ])
            : collect();

        return view('supervisor.kpi', compact('periods', 'period', 'scores'));
    }

    public function confirm(Request $request, KpiScore $kpiScore): RedirectResponse
    {
        $user = $request->user();
        $allowed = $user->isManagerHrd()
            || ($user->employee_id !== null && $kpiScore->employee()->where('supervisor_id', $user->employee_id)->exists());
        abort_unless($allowed && $user->employee_id !== $kpiScore->employee_id, 403, 'Anda hanya bisa mengonfirmasi KPI anggota tim Anda.');

        $kpiScore->update(['confirmed_by' => $user->id, 'confirmed_at' => now()]);

        return back()->with('status', 'Skor KPI '.$kpiScore->employee->full_name.' dikonfirmasi.');
    }
}
