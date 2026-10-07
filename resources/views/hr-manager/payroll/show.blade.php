@php
    use App\Support\Money;
    $settings = app(\App\Services\Payroll\PayrollSettings::class);
    $draftCount = $period->payslips()->where('status', 'draft')->count();
    $finalCount = $period->payslips()->whereIn('status', ['locked', 'published'])->count();
    $lockedCount = $period->payslips()->where('status', 'locked')->count();
    $bsi = app(\App\Services\Payroll\BsiPayrollExportService::class)->summary($period);
@endphp
<x-layouts.app :title="'Payroll '.$period->period_name">
    <div x-data="{ bsi: {{ $errors->has('debit_account') || $errors->has('effective_date') ? 'true' : 'false' }}, approve: false }">
        <nav class="text-sm text-slate-500"><a href="{{ route('hr-manager.payroll.index') }}" class="hover:text-brand-700">Payroll</a> / <span class="text-slate-700">{{ $period->period_name }}</span></nav>
        <div class="mt-1 flex flex-wrap items-start justify-between gap-4">
            <div>
                <h1 class="text-2xl font-bold text-slate-900">Payroll {{ $period->period_name }}</h1>
                <div class="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-500">
                    <x-status-badge :status="$period->status" :label="$period->statusLabel()" />
                    <span>{{ $period->cutoffLabel() }} · dibayar {{ \App\Support\Tanggal::panjang($period->payment_date) }}</span>
                    @if ($period->approved_at)
                        <span>· disetujui {{ $period->approver?->name }} {{ $period->approved_at->format('d/m/Y H:i') }}</span>
                    @endif
                </div>
            </div>
            <div class="flex flex-wrap gap-2">
                @if ($period->isDraft())
                    <form method="POST" action="{{ route('hr-manager.payroll.generate', $period) }}">
                        @csrf
                        <button class="btn btn-secondary" @disabled($period->isGenerating())>{{ $totals->n ? 'Generate Ulang Draft' : 'Generate Draft' }}</button>
                    </form>
                @endif
                @if ($draftCount > 0)
                    <button type="button" class="btn btn-primary" @click="approve = true" @disabled($period->isGenerating())>Approve &amp; Lock Semua ({{ $draftCount }})</button>
                @endif
                @if ($finalCount > 0)
                    <button type="button" class="btn btn-success" @click="bsi = true">Export Transfer BSI</button>
                @endif
                @if ($lockedCount > 0 && ! $period->isGenerating())
                    <form method="POST" action="{{ route('hr-manager.payroll.retry-pdf', $period) }}" title="Kirim ulang slip terkunci ke antrean pembuatan PDF">
                        @csrf
                        <button class="btn btn-secondary">Buat Ulang PDF ({{ $lockedCount }})</button>
                    </form>
                @endif
                @if ($period->status === 'published')
                    <form method="POST" action="{{ route('hr-manager.payroll.close', $period) }}">
                        @csrf
                        <button class="btn btn-secondary">Tutup Periode</button>
                    </form>
                @endif
            </div>
        </div>

        <div class="mt-4"><livewire:period-status-panel :period="$period" /></div>
        @if ($period->generation_error && ! $period->isGenerating() && $period->generation_status !== 'failed')
            <div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <span class="font-semibold">Generate selesai dengan catatan:</span> {{ $period->generation_error }}
            </div>
        @endif

        {{-- Ringkasan --}}
        <div class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
            @foreach ([
                ['Karyawan', number_format($totals->n ?? 0, 0, ',', '.'), 'text-slate-900'],
                ['Total Bruto', Money::rupiah($totals->gross ?? 0), 'text-slate-900'],
                ['Setoran BPJS', Money::rupiah($totals->bpjs ?? 0), 'text-slate-900'],
                ['PPh 21', Money::rupiah($totals->pph21 ?? 0), 'text-slate-900'],
                ['Total THP Ditransfer', Money::rupiah($totals->thp ?? 0), 'text-emerald-700'],
            ] as [$label, $value, $color])
                <div class="card px-4 py-3">
                    <div class="text-xs font-semibold tracking-wide text-slate-500 uppercase">{{ $label }}</div>
                    <div class="mt-1 text-lg font-bold tabular-nums {{ $color }}">{{ $value }}</div>
                </div>
            @endforeach
        </div>

        {{-- Filter --}}
        <form method="GET" class="mt-5 flex flex-wrap items-center gap-2">
            <input type="search" name="q" value="{{ $search }}" placeholder="Cari nama, NIK, divisi…" class="input w-64">
            <select name="status" class="input w-52" onchange="this.form.submit()">
                <option value="">Semua status</option>
                @foreach (['draft' => 'Draft', 'locked' => 'Terkunci (PDF diproses)', 'published' => 'Published', 'adjusted' => 'Disesuaikan manual'] as $value => $label)
                    <option value="{{ $value }}" @selected($status === $value)>{{ $label }}</option>
                @endforeach
            </select>
            <button class="btn btn-secondary">Terapkan</button>
        </form>

        <div class="card mt-3 overflow-x-auto">
            <table class="table-base">
                <thead>
                <tr>
                    <th>Karyawan</th>
                    <th>PTKP / Pajak</th>
                    <th class="num">Hadir</th>
                    <th class="num">Penalti</th>
                    <th class="num">Bruto</th>
                    <th class="num">Potongan</th>
                    <th class="num">PPh 21</th>
                    <th class="num">THP</th>
                    <th>Status</th>
                    <th></th>
                </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                @forelse ($payslips as $slip)
                    <tr>
                        <td>
                            <a href="{{ route('hr-manager.payroll.workbench', [$period, $slip->employee_id]) }}" class="font-semibold text-slate-900 hover:text-brand-700">{{ $slip->employee_name }}</a>
                            <div class="text-xs text-slate-500">{{ $slip->employee_nik }} · {{ $slip->department }}</div>
                        </td>
                        <td class="text-xs">
                            {{ $slip->ptkp_status }} ·
                            {{ $slip->pph21_method === 'PASAL17' ? 'Pasal 17' : 'TER '.$slip->ter_category.' '.Money::bpToPercent((int) round(($slip->ter_rate ?? 0) * 100), true) }}
                        </td>
                        <td class="num">{{ $slip->attended_days }}</td>
                        <td class="num">{{ $slip->late_penalty_days ? $slip->late_penalty_days.' hr' : '–' }}</td>
                        <td class="num">{{ Money::format($slip->gross_earnings) }}</td>
                        <td class="num text-red-700">{{ Money::format($slip->total_deductions) }}</td>
                        <td class="num">{{ Money::format($slip->pph21_amount) }}</td>
                        <td @class(['num font-bold', 'text-emerald-700' => $slip->take_home_pay >= 0, 'text-red-700' => $slip->take_home_pay < 0])>{{ Money::format($slip->take_home_pay) }}</td>
                        <td>
                            <x-status-badge :status="$slip->status" />
                            @if ($slip->is_manually_adjusted)<span class="badge bg-amber-50 text-amber-800 ring-1 ring-amber-200" title="{{ $slip->adjustment_notes }}">manual</span>@endif
                            @if ($slip->take_home_pay < 0)<span class="badge bg-red-100 text-red-800">THP negatif</span>@endif
                            @if ($slip->bsi_exported_at)<span class="badge badge-muted" title="Masuk file transfer {{ $slip->bsi_exported_at->format('d/m/Y H:i') }}">BSI ✓</span>@endif
                            @if ($slip->pdf_error)<span class="badge bg-red-100 text-red-800" title="{{ $slip->pdf_error }}">PDF gagal</span>@endif
                        </td>
                        <td class="text-right">
                            <a href="{{ route('hr-manager.payroll.workbench', [$period, $slip->employee_id]) }}" class="btn btn-secondary btn-sm">{{ $slip->isDraft() ? 'Tinjau / Edit' : 'Lihat' }}</a>
                        </td>
                    </tr>
                @empty
                    <tr><td colspan="10" class="py-10 text-center text-slate-500">
                        {{ $search || $status ? 'Tidak ada slip yang cocok dengan filter.' : 'Belum ada slip. Klik “Generate Draft”.' }}
                    </td></tr>
                @endforelse
                </tbody>
            </table>
        </div>

        @if ($exports->isNotEmpty())
            <div class="card mt-5">
                <div class="card-header"><h2 class="card-title">Riwayat file transfer bank</h2></div>
                <table class="table-base">
                    <thead><tr><th>Waktu</th><th>File</th><th>Rek. Debet</th><th>Tgl Efektif</th><th class="num">Baris</th><th class="num">Total</th><th>Oleh</th></tr></thead>
                    <tbody class="divide-y divide-slate-100">
                    @foreach ($exports as $export)
                        <tr>
                            <td>{{ $export->created_at->format('d/m/Y H:i') }}</td>
                            <td class="font-mono text-xs">{{ $export->file_name }}</td>
                            <td>{{ $export->debit_account }}</td>
                            <td>{{ $export->effective_date->format('d/m/Y') }}</td>
                            <td class="num">{{ $export->row_count }}</td>
                            <td class="num">{{ Money::format($export->total_amount) }}</td>
                            <td>{{ $export->user?->name }}</td>
                        </tr>
                    @endforeach
                    </tbody>
                </table>
            </div>
        @endif

        {{-- Modal Approve semua --}}
        <div x-cloak x-show="approve" class="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4" @keydown.escape.window="approve = false">
            <div class="card w-full max-w-md p-6" @click.outside="approve = false">
                <h3 class="text-lg font-bold">Approve &amp; Lock {{ $draftCount }} slip draft?</h3>
                <p class="mt-2 text-sm text-slate-600">Data dibekukan, PDF ber-password DDMMYY dibuat di antrean, lalu slip terbit ke Rumatku dan karyawan menerima notifikasi.</p>
                <form method="POST" action="{{ route('hr-manager.payroll.approve-all', $period) }}" class="mt-5 flex justify-end gap-2">
                    @csrf
                    <button type="button" class="btn btn-secondary" @click="approve = false">Batal</button>
                    <button class="btn btn-primary">Ya, Approve &amp; Lock</button>
                </form>
            </div>
        </div>

        {{-- Modal Export BSI (Modul 5A) --}}
        <div x-cloak x-show="bsi" class="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4" @keydown.escape.window="bsi = false">
            <div class="card w-full max-w-md p-6" @click.outside="bsi = false">
                <h3 class="text-lg font-bold">Export Transfer BSI</h3>
                <p class="mt-1 text-sm text-slate-600">File Bulk Payment BSI Corporate. Slip yang sudah pernah masuk file tidak diikutkan lagi (mencegah transfer ganda).</p>
                <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                    <div class="rounded-lg bg-emerald-50 px-2 py-2"><div class="text-lg font-bold text-emerald-700">{{ $bsi['pending'] }}</div>siap diekspor<div class="font-semibold text-emerald-800">{{ Money::rupiah($bsi['pending_total']) }}</div></div>
                    <div class="rounded-lg bg-slate-100 px-2 py-2"><div class="text-lg font-bold text-slate-700">{{ $bsi['exported'] }}</div>sudah diekspor</div>
                    <div @class(['rounded-lg px-2 py-2', 'bg-amber-50' => $bsi['drafts'] > 0, 'bg-slate-50' => $bsi['drafts'] === 0])><div class="text-lg font-bold text-amber-700">{{ $bsi['drafts'] }}</div>masih draft (tidak ikut)</div>
                </div>
                <form method="POST" action="{{ route('hr-manager.payroll.export-bsi', $period) }}" class="mt-4 space-y-4" @submit="setTimeout(() => bsi = false, 300)">
                    @csrf
                    <div>
                        <label class="label" for="debit_account">Rekening debet operasional BSI</label>
                        <input id="debit_account" name="debit_account" value="{{ old('debit_account', $settings->get('BSI_DEBIT_ACCOUNT')) }}" class="input font-mono" required>
                        @error('debit_account')<p class="field-error">{{ $message }}</p>@enderror
                    </div>
                    <div>
                        <label class="label" for="effective_date">Tanggal efektif transfer</label>
                        <input id="effective_date" type="date" name="effective_date" value="{{ old('effective_date', $period->payment_date->toDateString()) }}" class="input" required>
                        @error('effective_date')<p class="field-error">{{ $message }}</p>@enderror
                    </div>
                    @if ($bsi['exported'] > 0)
                        <label class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                            <input type="checkbox" name="include_exported" value="1" class="mt-0.5 rounded border-amber-300">
                            <span>Ekspor ulang termasuk {{ $bsi['exported'] }} slip yang sudah pernah diekspor — <b>hanya</b> bila file sebelumnya gagal diunggah ke BSI.</span>
                        </label>
                    @endif
                    <p class="text-xs text-slate-500">Pemisah kolom: “{{ $settings->get('BSI_CSV_SEPARATOR') }}” (ubah di Pengaturan). Rekening BSI → INTERNAL BSI, bank lain → BI-FAST (≤ Rp250 jt) atau SKN.</p>
                    <div class="flex justify-end gap-2">
                        <button type="button" class="btn btn-secondary" @click="bsi = false">Batal</button>
                        <button class="btn btn-success">Unduh CSV</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</x-layouts.app>
