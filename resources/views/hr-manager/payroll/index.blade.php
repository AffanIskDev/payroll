@php use App\Support\Money; @endphp
<x-layouts.app title="Payroll">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Periode Payroll</h1>
            <p class="mt-1 text-sm text-slate-500">Cut-off tanggal 1 s/d akhir bulan · dibayar tanggal 1 bulan berikutnya · standar 25 hari kerja.</p>
        </div>
        <form method="POST" action="{{ route('hr-manager.payroll.store') }}" class="card flex flex-wrap items-end gap-3 p-3">
            @csrf
            <div>
                <label class="label" for="month">Periode baru</label>
                <input id="month" type="month" name="month" value="{{ old('month', $suggested) }}" class="input" required>
            </div>
            <label class="mb-2 flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" name="generate" value="1" checked class="rounded border-slate-300"> langsung generate draft
            </label>
            <button class="btn btn-primary" type="submit">Buat Periode</button>
        </form>
    </div>

    <div class="card mt-6 overflow-x-auto">
        <table class="table-base">
            <thead>
            <tr>
                <th>Periode</th>
                <th>Tgl Bayar</th>
                <th>Status</th>
                <th class="num">Karyawan</th>
                <th class="num">Total Bruto</th>
                <th class="num">Total Potongan</th>
                <th class="num">Total THP</th>
                <th>Catatan</th>
                <th></th>
            </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            @forelse ($periods as $period)
                <tr>
                    <td>
                        <a href="{{ route('hr-manager.payroll.show', $period) }}" class="font-semibold text-brand-700 hover:underline">{{ $period->period_name }}</a>
                        <div class="text-xs text-slate-500">{{ $period->cutoffLabel() }}</div>
                    </td>
                    <td>{{ \App\Support\Tanggal::panjang($period->payment_date) }}</td>
                    <td>
                        <x-status-badge :status="$period->status" :label="$period->statusLabel()" />
                        @if ($period->isGenerating())
                            <span class="badge badge-locked">Generate berjalan…</span>
                        @endif
                    </td>
                    <td class="num">{{ $period->payslips_count }}</td>
                    <td class="num">{{ Money::format($period->total_gross) }}</td>
                    <td class="num">{{ Money::format($period->total_deductions) }}</td>
                    <td class="num font-semibold text-emerald-700">{{ Money::format($period->total_thp) }}</td>
                    <td class="text-xs text-slate-500">
                        @if ($period->draft_count){{ $period->draft_count }} draft · @endif
                        @if ($period->adjusted_count){{ $period->adjusted_count }} disesuaikan · @endif
                        {{ $period->published_count }} terbit
                    </td>
                    <td class="text-right"><a href="{{ route('hr-manager.payroll.show', $period) }}" class="btn btn-secondary btn-sm">Buka</a></td>
                </tr>
            @empty
                <tr><td colspan="9" class="py-10 text-center text-slate-500">Belum ada periode. Buat periode pertama di atas.</td></tr>
            @endforelse
            </tbody>
        </table>
    </div>
</x-layouts.app>
