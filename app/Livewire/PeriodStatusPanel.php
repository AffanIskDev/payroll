<?php

namespace App\Livewire;

use App\Models\PayrollPeriod;
use App\Models\Payslip;
use Illuminate\Support\Facades\Gate;
use Livewire\Attributes\Locked;
use Livewire\Component;

/** Progres generate batch & pembuatan PDF; memuat ulang halaman saat proses selesai. */
class PeriodStatusPanel extends Component
{
    #[Locked]
    public int $periodId;

    public bool $wasActive = false;

    public function mount(PayrollPeriod $period): void
    {
        Gate::authorize('manage-payroll');
        $this->periodId = $period->id;
        $this->wasActive = $this->isActive($period);
    }

    public function hydrate(): void
    {
        Gate::authorize('manage-payroll');
    }

    public function render()
    {
        $period = PayrollPeriod::findOrFail($this->periodId);
        $counts = $period->payslips()->selectRaw('status, COUNT(*) as total')->groupBy('status')->pluck('total', 'status');
        $active = $this->isActive($period, $counts['locked'] ?? 0);

        if ($this->wasActive && ! $active) {
            $this->redirectRoute('hr-manager.payroll.show', $period);
        }
        $this->wasActive = $active;

        return view('livewire.period-status-panel', [
            'period' => $period,
            'active' => $active,
            'draft' => (int) ($counts[Payslip::STATUS_DRAFT] ?? 0),
            'locked' => (int) ($counts[Payslip::STATUS_LOCKED] ?? 0),
            'published' => (int) ($counts[Payslip::STATUS_PUBLISHED] ?? 0),
        ]);
    }

    private function isActive(PayrollPeriod $period, ?int $locked = null): bool
    {
        $locked ??= $period->payslips()->where('status', Payslip::STATUS_LOCKED)->count();

        return $period->isGenerating() || $locked > 0;
    }
}
