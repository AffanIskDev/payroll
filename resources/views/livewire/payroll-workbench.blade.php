@php
    use App\Support\Money;
    $propertyFor = array_flip($fields);
    $period = $payslip->period;
    $late = $system['late'] ?? [];
    $tax = $preview->pph21_breakdown ?? [];
@endphp
<div @if ($payslip->status === 'locked') wire:poll.3s @endif class="pb-40">
    {{-- Header & aksi --}}
    <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
            <nav class="flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
                <a href="{{ route('hr-manager.payroll.index') }}" class="hover:text-brand-700">Payroll</a>
                <span>/</span>
                <a href="{{ route('hr-manager.payroll.show', $period) }}" class="hover:text-brand-700">{{ $period->period_name }}</a>
                <span>/</span>
                <span class="font-medium text-slate-700">{{ $payslip->employee_name }}</span>
            </nav>
            <h1 class="mt-1 text-2xl font-bold text-slate-900">{{ $payslip->employee_name }}</h1>
            <div class="mt-2 flex flex-wrap items-center gap-2">
                <x-status-badge :status="$payslip->status" />
                @if ($preview->is_manually_adjusted)
                    <span class="badge bg-amber-50 text-amber-800 ring-1 ring-amber-200">Disesuaikan manual</span>
                @endif
                @if ($dirty)
                    <span class="badge bg-blue-50 text-blue-700 ring-1 ring-blue-200">Ada perubahan belum disimpan</span>
                @endif
                <span class="text-xs text-slate-500">{{ $positionLabel }}</span>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
            <a @if ($prevEmployeeId) href="{{ route('hr-manager.payroll.workbench', [$period, $prevEmployeeId]) }}" @endif
               @class(['btn btn-secondary btn-sm', 'pointer-events-none opacity-40' => ! $prevEmployeeId]) title="Karyawan sebelumnya">&larr;</a>
            <a @if ($nextEmployeeId) href="{{ route('hr-manager.payroll.workbench', [$period, $nextEmployeeId]) }}" @endif
               @class(['btn btn-secondary btn-sm', 'pointer-events-none opacity-40' => ! $nextEmployeeId]) title="Karyawan berikutnya">&rarr;</a>
            @if ($editable)
                <button type="button" wire:click="saveDraft" wire:loading.attr="disabled" class="btn btn-secondary" @disabled(! $dirty && ! $stale)>
                    <span wire:loading.remove wire:target="saveDraft">Simpan Draft</span>
                    <span wire:loading wire:target="saveDraft">Menyimpan…</span>
                </button>
                <button type="button" wire:click="$set('confirmingLock', true)" class="btn btn-primary" @if ($blocking) disabled title="{{ $blocking }}" @endif>Approve &amp; Lock</button>
            @endif
        </div>
    </div>

    @if ($flash)
        <div class="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{{ $flash }}</div>
    @endif
    @error('general')
        <div class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">{{ $message }}</div>
    @enderror
    @if ($stale)
        <div class="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
            <span class="font-semibold">Data berubah sejak slip ini dihitung</span> (profil gaji, pengaturan, atau slip bulan lain).
            Angka di layar sudah memakai data terbaru: THP tersimpan {{ Money::rupiah($payslip->take_home_pay) }} → {{ Money::rupiah($preview->take_home_pay) }}.
            Angka terbaru ini yang akan tersimpan saat <b>Simpan Draft</b> atau <b>Approve &amp; Lock</b>.
        </div>
    @endif
    @if ($blocking)
        <div class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <span class="font-semibold">Belum bisa di-approve:</span> {{ $blocking }}
        </div>
    @endif

    {{-- Metadata karyawan --}}
    <div class="card mt-5 grid gap-x-8 gap-y-3 p-5 sm:grid-cols-2 lg:grid-cols-4">
        @foreach ([
            ['Nama Lengkap', $payslip->employee_name],
            ['NIK / Employee ID', $payslip->employee_nik],
            ['Status PTKP & Kategori', app(\App\Services\Payroll\PayslipPresenter::class)->taxStatusLabel($preview)],
            ['Rekening Tujuan', \App\Support\BankDirectory::label($payslip->bank_name).' • '.$payslip->bank_account_number],
            ['Gaji Pokok', Money::rupiah($payslip->basic_salary)],
            ['Tunjangan Kehadiran Basis', Money::rupiah($payslip->attendance_allowance)],
            ['Basis Upah BPJS Kesehatan', Money::rupiah($preview->bpjs_kes_base_salary).(($preview->bpjs_breakdown['umk_floor_applied'] ?? false) ? ' (floor UMK)' : '')],
            ['Basis Upah BPJS Ketenagakerjaan', Money::rupiah($preview->bpjs_tk_base_salary).' · JP '.Money::rupiah($preview->bpjs_jp_base_salary)],
        ] as [$label, $value])
            <div>
                <div class="text-xs font-medium tracking-wide text-slate-500 uppercase">{{ $label }}</div>
                <div class="mt-0.5 text-sm font-semibold text-slate-900">{{ $value }}</div>
            </div>
        @endforeach
    </div>

    {{-- Ringkasan presensi --}}
    <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        @foreach ([
            ['Hari Hadir', $payslip->attended_days.' hari'],
            ['Izin / Sakit / Cuti', $payslip->leave_sick_days.' hari'],
            ['Alpa', $payslip->absent_days.' hari'],
            ['Total Terlambat', $payslip->late_minutes_total.' menit'],
            ['Jam Lembur (disetujui)', rtrim(rtrim(number_format($payslip->overtime_hours, 2, ',', '.'), '0'), ',').' jam'],
            ['Penalti Terlambat', $payslip->late_penalty_days.' hari'.($payslip->late_penalty_rule ? ' · '.$payslip->late_penalty_rule : '')],
        ] as [$label, $value])
            <div class="rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3">
                <div class="text-[11px] font-bold tracking-wide text-blue-700 uppercase">{{ $label }}</div>
                <div class="mt-1 text-base font-bold text-blue-950">{{ $value }}</div>
            </div>
        @endforeach
    </div>

    {{-- Dua kolom komponen --}}
    <div class="mt-5 grid gap-5 lg:grid-cols-2">
        @foreach ([
            ['Komponen Penerimaan (A)', $slip['earnings'], 'Total Penghasilan Bruto', $slip['gross'], 'emerald'],
            ['Komponen Potongan (B)', $slip['deductions'], 'Total Potongan', $slip['total_deductions'], 'red'],
        ] as [$title, $rows, $totalLabel, $total, $tone])
            <section class="card overflow-hidden">
                <div @class([
                    'flex items-center justify-between border-b px-5 py-3 text-sm font-bold tracking-wide uppercase',
                    'border-emerald-200 bg-emerald-50 text-emerald-800' => $tone === 'emerald',
                    'border-red-200 bg-red-50 text-red-800' => $tone === 'red',
                ])>
                    <span>{{ $title }}</span><span>Jumlah (Rp)</span>
                </div>
                <div class="divide-y divide-slate-100">
                    @foreach ($rows as $row)
                        @php $prop = $propertyFor[$row['key']] ?? null; $isEditable = $editable && $prop; @endphp
                        <div @class(['px-5 py-3', 'bg-amber-50/70' => $isEditable])>
                            <div class="flex items-start justify-between gap-4">
                                <div class="min-w-0">
                                    <div class="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
                                        {{ $row['label'] }}
                                        @if ($isEditable)<span class="badge badge-editable">EDITABLE</span>@endif
                                    </div>
                                    <div class="mt-0.5 text-xs text-slate-500">{{ $row['caption'] }}</div>
                                </div>
                                @if ($isEditable)
                                    <div class="w-44 shrink-0">
                                        <div class="relative">
                                            <span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs font-semibold text-slate-400">Rp</span>
                                            <input type="number" min="0" step="1" inputmode="numeric"
                                                   wire:model.live.debounce.350ms="{{ $prop }}"
                                                   @class(['input pl-9 text-right font-semibold tabular-nums ring-amber-300', 'input-error' => $errors->has($prop)])
                                                   aria-label="{{ $row['label'] }}">
                                        </div>
                                        @php $systemValue = (int) ($system[$row['key']] ?? 0); @endphp
                                        @if ((int) $row['amount'] !== $systemValue)
                                            <button type="button" wire:click="resetField('{{ $prop }}')" class="mt-1 w-full text-right text-[11px] font-medium text-amber-800 hover:underline">
                                                Sistem: {{ Money::rupiah($systemValue) }} · kembalikan
                                            </button>
                                        @endif
                                    </div>
                                @else
                                    <div class="shrink-0 text-right text-sm font-bold text-slate-900 tabular-nums">{{ Money::format($row['amount']) }}</div>
                                @endif
                            </div>
                            @if ($prop) @error($prop)<p class="field-error text-right">{{ $message }}</p>@enderror @endif
                        </div>
                    @endforeach
                </div>
                <div class="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-3.5">
                    <span class="text-sm font-bold text-slate-800">{{ $totalLabel }}</span>
                    <span @class(['text-lg font-bold tabular-nums', 'text-emerald-700' => $tone === 'emerald', 'text-red-700' => $tone === 'red'])>{{ Money::rupiah($total) }}</span>
                </div>
            </section>
        @endforeach
    </div>

    {{-- Alasan penyesuaian & dasar hitung --}}
    <div class="mt-5 grid gap-5 lg:grid-cols-5">
        <div class="space-y-5 lg:col-span-3">
            @if ($editable)
                <section class="card p-5">
                    <label class="label" for="adjustmentNotes">Alasan penyesuaian <span class="normal-case text-slate-400">(wajib setiap mengubah nilai)</span></label>
                    <textarea id="adjustmentNotes" rows="2" wire:model="adjustmentNotes" placeholder="mis. Bonus kinerja Q1 disetujui Direksi"
                              @class(['input', 'input-error' => $errors->has('adjustmentNotes')])></textarea>
                    @error('adjustmentNotes')<p class="field-error">{{ $message }}</p>@enderror
                    @if ($payslip->adjustment_notes)
                        <p class="mt-2 text-xs text-slate-500">Catatan terakhir: “{{ $payslip->adjustment_notes }}”</p>
                    @endif
                </section>
            @endif

            <section class="card">
                <div class="card-header"><h2 class="card-title">Riwayat penyesuaian &amp; status</h2></div>
                @forelse ($payslip->adjustments as $adj)
                    <div class="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3 last:border-0">
                        <div class="text-sm">
                            <div class="font-medium text-slate-800">{{ $adj->fieldLabel() }}:
                                @if ($adj->field === 'status')
                                    {{ $adj->old_value }} → <span class="font-semibold">{{ $adj->new_value }}</span>
                                @else
                                    {{ Money::rupiah($adj->old_value) }} → <span class="font-semibold">{{ Money::rupiah($adj->new_value) }}</span>
                                @endif
                            </div>
                            @if ($adj->reason)<div class="text-xs text-slate-500">“{{ $adj->reason }}”</div>@endif
                        </div>
                        <div class="shrink-0 text-right text-xs text-slate-500">
                            {{ $adj->user?->name ?? 'Sistem' }}<br>{{ $adj->created_at?->format('d/m/Y H:i') }}
                        </div>
                    </div>
                @empty
                    <p class="px-5 py-4 text-sm text-slate-500">Belum ada penyesuaian manual.</p>
                @endforelse
            </section>
        </div>

        <section class="card lg:col-span-2">
            <div class="card-header"><h2 class="card-title">Dasar perhitungan</h2></div>
            <dl class="divide-y divide-slate-100 text-sm">
                <div class="px-5 py-3">
                    <dt class="font-semibold text-slate-700">Penalti keterlambatan (non-duplikasi)</dt>
                    <dd class="mt-1 grid grid-cols-3 gap-2 text-xs text-slate-600">
                        <span>Rule A (≥60 mnt): <b>{{ $late['rule_a_days'] ?? 0 }}</b> hr</span>
                        <span>Rule B (3×≥15 mnt): <b>{{ $late['rule_b_days'] ?? 0 }}</b> hr</span>
                        <span>Rule C (Σ/60): <b>{{ $late['rule_c_days'] ?? 0 }}</b> hr</span>
                    </dd>
                    <dd class="mt-1 text-xs text-slate-500">Diambil tertinggi: {{ $late['penalty_days'] ?? 0 }} hari × Tunj. Kehadiran / {{ $late['work_days_basis'] ?? 25 }} (maks. 100% tunjangan).</dd>
                </div>
                <div class="px-5 py-3">
                    <dt class="font-semibold text-slate-700">BPJS (Full Gross)</dt>
                    <dd class="mt-1 text-xs text-slate-600">
                        Kes: basis {{ Money::rupiah($preview->bpjs_kes_base_salary) }} → tunjangan 4% {{ Money::rupiah($preview->tunjangan_bpjs_kes) }}, setor 5% {{ Money::rupiah($preview->iuran_bpjs_kes_total) }}<br>
                        TK: tunjangan {{ Money::rupiah($preview->tunjangan_bpjs_tk) }}, setor total {{ Money::rupiah($preview->iuran_bpjs_tk_total) }} (porsi pekerja JHT+JP {{ Money::rupiah($preview->employee_jht_jp) }})
                    </dd>
                </div>
                <div class="px-5 py-3">
                    <dt class="font-semibold text-slate-700">PPh 21 — {{ $preview->pph21_method === 'PASAL17' ? 'Rekonsiliasi Pasal 17 (masa terakhir)' : 'TER bulanan' }}</dt>
                    @if ($preview->pph21_method === 'PASAL17')
                        <dd class="mt-1 space-y-0.5 text-xs text-slate-600">
                            @foreach ([
                                ['Bruto setahun', $tax['gross_year'] ?? 0], ['Biaya jabatan', $tax['biaya_jabatan'] ?? 0],
                                ['Iuran JHT+JP pekerja', $tax['jht_jp_year'] ?? 0], ['Neto setahun', $tax['neto_year'] ?? 0],
                                ['PTKP ('.($tax['ptkp_status'] ?? '').')', $tax['ptkp'] ?? 0], ['PKP', $tax['pkp'] ?? 0],
                                ['PPh 21 setahun', $tax['pph21_annual'] ?? 0], ['Sudah dipotong', $tax['pph21_already_paid'] ?? 0],
                            ] as [$k, $v])
                                <div class="flex justify-between"><span>{{ $k }}</span><span class="tabular-nums">{{ Money::rupiah($v) }}</span></div>
                            @endforeach
                            <div class="flex justify-between border-t border-slate-200 pt-1 font-semibold text-slate-800"><span>PPh 21 masa ini</span><span class="tabular-nums">{{ Money::rupiah($preview->pph21_amount) }}</span></div>
                            @foreach ($tax['warnings'] ?? [] as $w)<div class="mt-1 rounded bg-amber-50 px-2 py-1 text-amber-800">{{ $w }}</div>@endforeach
                        </dd>
                    @else
                        <dd class="mt-1 text-xs text-slate-600">
                            Kategori {{ $tax['category'] ?? $preview->ter_category }} · lapisan bruto
                            {{ Money::rupiah($tax['lower'] ?? 0) }} – {{ isset($tax['upper']) && $tax['upper'] ? Money::rupiah($tax['upper']) : '∞' }}
                            · tarif {{ Money::bpToPercent((int) ($tax['rate_bp'] ?? 0), true) }} × bruto {{ Money::rupiah($preview->gross_earnings) }}
                        </dd>
                    @endif
                </div>
            </dl>
        </section>
    </div>

    {{-- Bar THP menempel di bawah --}}
    <div class="fixed inset-x-0 bottom-0 z-30 border-t border-slate-800 bg-ink/95 text-white shadow-2xl backdrop-blur">
        <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <div class="min-w-0">
                <div class="text-xs font-bold tracking-widest text-slate-400 uppercase">Take Home Pay (Gaji Bersih Diterima)</div>
                <div class="flex flex-wrap items-baseline gap-x-4">
                    <span class="text-3xl font-bold text-emerald-400 tabular-nums" wire:loading.class="opacity-60">{{ Money::rupiah($slip['thp']) }}</span>
                    <span class="text-xs text-slate-400">Penerimaan {{ Money::rupiah($slip['gross']) }} − Potongan {{ Money::rupiah($slip['total_deductions']) }}</span>
                </div>
                <div class="truncate text-sm text-slate-300 italic">“{{ $slip['terbilang'] }}”</div>
            </div>
            <div class="flex shrink-0 flex-wrap items-center gap-2">
                <a href="{{ route('hr-manager.payroll.preview-pdf', [$period, $payslip->employee_id]) }}" target="_blank" class="btn bg-white/10 text-white hover:bg-white/20">
                    Preview PDF Slip
                </a>
                @if ($payslip->pdf_path)
                    <a href="{{ route('hr-manager.payroll.pdf', [$period, $payslip->employee_id]) }}" class="btn bg-emerald-500 text-emerald-950 hover:bg-emerald-400">Unduh PDF terenkripsi</a>
                @endif
            </div>
        </div>
        @if ($dirty)
            <div class="bg-blue-600/90 px-4 py-1 text-center text-xs text-white">Pratinjau PDF memakai data tersimpan — klik “Simpan Draft” agar perubahan ikut tercetak.</div>
        @endif
    </div>

    {{-- Konfirmasi Approve & Lock --}}
    @if ($confirmingLock)
        <div class="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4" wire:keydown.escape.window="$set('confirmingLock', false)">
            <div class="card w-full max-w-md p-6">
                <h3 class="text-lg font-bold text-slate-900">Approve &amp; Lock slip {{ $payslip->employee_name }}?</h3>
                <ul class="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                    <li>Data dibekukan dan tidak bisa diubah lagi.</li>
                    <li>PDF slip ber-password tanggal lahir (DDMMYY) dibuat di antrean.</li>
                    <li>Slip terbit di menu Slip Gaji Rumatku dan karyawan menerima notifikasi.</li>
                    @if ($dirty)<li class="font-medium text-blue-700">Perubahan yang belum disimpan akan disimpan dulu (alasan wajib diisi).</li>@endif
                </ul>
                <div class="mt-5 rounded-lg bg-slate-50 px-4 py-3 text-sm">THP final: <span class="font-bold text-emerald-700">{{ Money::rupiah($slip['thp']) }}</span></div>
                <div class="mt-5 flex justify-end gap-2">
                    <button type="button" class="btn btn-secondary" wire:click="$set('confirmingLock', false)">Batal</button>
                    <button type="button" class="btn btn-primary" wire:click="approveAndLock" wire:loading.attr="disabled">Ya, Approve &amp; Lock</button>
                </div>
            </div>
        </div>
    @endif
</div>
