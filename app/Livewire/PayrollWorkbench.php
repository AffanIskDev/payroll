<?php

namespace App\Livewire;

use App\Models\Payslip;
use App\Services\Payroll\PayrollPipelineService;
use App\Services\Payroll\PayslipApprovalService;
use App\Services\Payroll\PayslipPresenter;
use App\Support\Money;
use DomainException;
use Illuminate\Support\Facades\Gate;
use Illuminate\Validation\ValidationException;
use Livewire\Attributes\Locked;
use Livewire\Component;

/**
 * Workbench Manager HRD (Modul 2B): kolom EDITABLE (lembur, insentif KPI, bonus,
 * potongan keterlambatan, kasbon) langsung menghitung ulang bruto, PPh 21,
 * total potongan, THP, dan terbilang tanpa memuat ulang halaman.
 */
class PayrollWorkbench extends Component
{
    /** Properti Livewire → kolom payslip. */
    private const FIELDS = [
        'overtimePay' => 'overtime_pay',
        'kpiIncentive' => 'kpi_incentive',
        'additionalBonus' => 'additional_bonus',
        'latePenaltyAmount' => 'late_penalty_amount',
        'otherDeductions' => 'other_deductions',
    ];

    #[Locked]
    public int $payslipId;

    #[Locked]
    public ?int $prevEmployeeId = null;

    #[Locked]
    public ?int $nextEmployeeId = null;

    #[Locked]
    public string $positionLabel = '';

    /** Nilai kolom saat dimuat; hanya kolom yang diubah Manager yang dikirim sebagai override. */
    #[Locked]
    public array $loaded = [];

    /** Versi slip (updated_at) saat dimuat, untuk mencegah menimpa perubahan lain (lost update). */
    #[Locked]
    public ?string $version = null;

    public $overtimePay = 0;

    public $kpiIncentive = 0;

    public $additionalBonus = 0;

    public $latePenaltyAmount = 0;

    public $otherDeductions = 0;

    public string $adjustmentNotes = '';

    public bool $confirmingLock = false;

    public ?string $flash = null;

    public function mount(Payslip $payslip, ?int $prevEmployeeId = null, ?int $nextEmployeeId = null, string $positionLabel = ''): void
    {
        Gate::authorize('manage-payroll');

        $this->payslipId = $payslip->id;
        $this->prevEmployeeId = $prevEmployeeId;
        $this->nextEmployeeId = $nextEmployeeId;
        $this->positionLabel = $positionLabel;
        $this->fillFrom($payslip);
    }

    /** Otorisasi ulang di setiap request Livewire, bukan hanya saat mount. */
    public function hydrate(): void
    {
        Gate::authorize('manage-payroll');
    }

    protected function rules(): array
    {
        $allowance = $this->payslip()->attendance_allowance;

        return [
            'overtimePay' => ['nullable', 'numeric', 'min:0', 'max:10000000000'],
            'kpiIncentive' => ['nullable', 'numeric', 'min:0', 'max:10000000000'],
            'additionalBonus' => ['nullable', 'numeric', 'min:0', 'max:10000000000'],
            'latePenaltyAmount' => ['nullable', 'numeric', 'min:0', 'max:'.$allowance],
            'otherDeductions' => ['nullable', 'numeric', 'min:0', 'max:10000000000'],
            'adjustmentNotes' => ['nullable', 'string', 'max:1000'],
        ];
    }

    protected function validationAttributes(): array
    {
        return [
            'overtimePay' => 'Uang Lembur',
            'kpiIncentive' => 'Insentif KPI',
            'additionalBonus' => 'Bonus Tambahan',
            'latePenaltyAmount' => 'Potongan Keterlambatan',
            'otherDeductions' => 'Potongan Kasbon',
            'adjustmentNotes' => 'Alasan penyesuaian',
        ];
    }

    protected function messages(): array
    {
        return ['latePenaltyAmount.max' => 'Potongan keterlambatan tidak boleh melebihi Tunjangan Kehadiran.'];
    }

    public function updated(string $property): void
    {
        $this->flash = null;
        if (array_key_exists($property, self::FIELDS)) {
            $this->validateOnly($property);
        }
    }

    /** Kembalikan satu kolom ke nilai hasil hitung sistem. */
    public function resetField(string $property): void
    {
        if (! array_key_exists($property, self::FIELDS)) {
            return;
        }
        $system = $this->payslip()->system_values ?? [];
        $this->{$property} = Money::round($system[self::FIELDS[$property]] ?? 0);
        $this->resetValidation($property);
    }

    public function saveDraft(PayrollPipelineService $pipeline): void
    {
        Gate::authorize('manage-payroll');
        $this->persist($pipeline);
    }

    public function approveAndLock(PayrollPipelineService $pipeline, PayslipApprovalService $approval): void
    {
        Gate::authorize('manage-payroll');

        if ($this->isDirty() && ! $this->persist($pipeline)) {
            $this->confirmingLock = false;

            return;
        }

        try {
            // Dihitung ulang dengan data terkini di dalam lock(): angka terkunci = angka di layar.
            $approval->lock($this->payslip()->refresh(), auth()->user());
        } catch (DomainException $e) {
            $this->addError('general', $e->getMessage());
            $this->confirmingLock = false;
            $this->fillFrom($this->payslip());

            return;
        }

        $this->confirmingLock = false;
        $this->fillFrom($this->payslip());
        $this->flash = 'Slip disetujui & dikunci. PDF ber-password DDMMYY sedang dibuat lalu terbit ke Rumatku.';
    }

    public function render(PayrollPipelineService $pipeline, PayslipPresenter $presenter)
    {
        $payslip = Payslip::with(['period', 'employee.salaryProfile', 'adjustments.user', 'lockedBy'])->findOrFail($this->payslipId);
        $editable = $payslip->isDraft();

        $preview = $editable ? $pipeline->preview($payslip, $this->overrides()) : $payslip;
        $dirty = $editable && $this->isDirty();

        return view('livewire.payroll-workbench', [
            'payslip' => $payslip,
            'preview' => $preview,
            'slip' => $presenter->present($preview),
            'editable' => $editable,
            'dirty' => $dirty,
            // Data master/pengaturan/slip lain berubah sejak slip disimpan: layar sudah memakai data terbaru.
            'stale' => $editable && ! $dirty && $preview->take_home_pay !== $payslip->take_home_pay,
            'blocking' => $editable ? app(PayslipApprovalService::class)->blockingReason($preview) : null,
            'system' => $payslip->system_values ?? [],
            'fields' => self::FIELDS,
        ]);
    }

    private function persist(PayrollPipelineService $pipeline): bool
    {
        $this->validate();

        $current = $this->payslip();
        if ($this->version !== null && $this->versionOf($current) !== $this->version) {
            $this->fillFrom($current);
            $this->addError('general', 'Slip ini berubah sejak halaman dibuka (generate ulang atau disimpan di tab lain). '
                .'Nilai terbaru sudah dimuat — ulangi perubahan Anda.');

            return false;
        }

        try {
            $updated = $pipeline->recalculateSinglePayslip($this->payslip(), $this->overrides(), (int) auth()->id(), $this->adjustmentNotes);
        } catch (ValidationException $e) {
            $columnToProperty = array_flip(self::FIELDS);
            foreach ($e->errors() as $key => $messages) {
                $this->addError($columnToProperty[$key] ?? $key, $messages[0]);
            }

            return false;
        } catch (DomainException $e) {
            $this->addError('general', $e->getMessage());

            return false;
        }

        $this->adjustmentNotes = '';
        $this->fillFrom($updated);
        $this->flash = 'Draft disimpan dan riwayat penyesuaian dicatat.';

        return true;
    }

    /**
     * Override hanya untuk kolom yang diubah Manager di halaman ini; kolom lain
     * tetap memakai nilai tersimpan (sistem / override sebelumnya).
     *
     * @return array<string, int>
     */
    private function overrides(): array
    {
        $errors = $this->getErrorBag();
        $overrides = [];
        foreach (self::FIELDS as $property => $column) {
            $value = $this->{$property};
            if ($errors->has($property) || ! is_numeric($value) || $value < 0) {
                continue;
            }
            if (Money::round($value) !== ($this->loaded[$property] ?? null)) {
                $overrides[$column] = Money::round($value);
            }
        }

        return $overrides;
    }

    private function isDirty(): bool
    {
        foreach (array_keys(self::FIELDS) as $property) {
            if (is_numeric($this->{$property}) && Money::round($this->{$property}) !== ($this->loaded[$property] ?? null)) {
                return true;
            }
        }

        return false;
    }

    private function fillFrom(Payslip $payslip): void
    {
        foreach (self::FIELDS as $property => $column) {
            $this->{$property} = (int) $payslip->{$column};
            $this->loaded[$property] = (int) $payslip->{$column};
        }
        $this->version = $this->versionOf($payslip);
    }

    private function versionOf(Payslip $payslip): ?string
    {
        return $payslip->updated_at?->format('Y-m-d H:i:s');
    }

    private function payslip(): Payslip
    {
        return Payslip::with(['period', 'employee.salaryProfile'])->findOrFail($this->payslipId);
    }
}
