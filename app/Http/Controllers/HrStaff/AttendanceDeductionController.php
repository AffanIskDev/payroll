<?php

namespace App\Http\Controllers\HrStaff;

use App\Http\Controllers\Controller;
use App\Models\PayrollPeriod;
use Illuminate\Http\Request;
use Illuminate\View\View;

/**
 * Staff HRD: tinjau draft potongan keterlambatan & ketidakhadiran (read-only).
 * Gaji pokok/THP tidak ditampilkan, dan karyawan manajemen disembunyikan
 * dari Staff HRD (PRD bab 2).
 */
class AttendanceDeductionController extends Controller
{
    public function index(Request $request, ?PayrollPeriod $period = null): View
    {
        $periods = PayrollPeriod::query()->orderByDesc('start_date')->get(['id', 'period_name', 'status', 'start_date']);
        $period ??= $periods->first();

        $canSeeManagement = $request->user()->isManagerHrd();

        $rows = $period
            ? $period->payslips()
                ->with('employee:id,is_management')
                ->when(! $canSeeManagement, fn ($q) => $q->whereHas('employee', fn ($e) => $e->where('is_management', false)))
                ->orderByDesc('late_penalty_days')->orderBy('employee_name')
                ->get([
                    'id', 'employee_id', 'employee_nik', 'employee_name', 'department', 'status', 'attended_days',
                    'leave_sick_days', 'absent_days', 'late_minutes_total', 'late_count_15', 'late_days_60',
                    'late_penalty_days', 'late_penalty_rule', 'late_penalty_amount', 'attendance_allowance', 'system_values',
                ])
            : collect();

        return view('hr-staff.attendance', compact('periods', 'period', 'rows', 'canSeeManagement'));
    }
}
