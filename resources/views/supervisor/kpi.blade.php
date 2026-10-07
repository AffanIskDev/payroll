@php use App\Support\Money; @endphp
<x-layouts.app title="KPI Tim">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Konfirmasi KPI Tim</h1>
            <p class="mt-1 max-w-2xl text-sm text-slate-500">Skor kinerja dari modul KPI ROSY. Insentif dihitung otomatis dari tabel konversi; konfirmasi Anda tercatat sebagai jejak persetujuan.</p>
        </div>
        @if ($periods->isNotEmpty())
            <form method="GET" onchange="window.location = '{{ url('/supervisor/kpi') }}/' + this.period.value">
                <select name="period" class="input w-56">
                    @foreach ($periods as $p)<option value="{{ $p->id }}" @selected($period && $p->id === $period->id)>{{ $p->period_name }}</option>@endforeach
                </select>
            </form>
        @endif
    </div>

    <div class="card mt-6 overflow-x-auto">
        <table class="table-base">
            <thead><tr><th>Anggota Tim</th><th>Jabatan</th><th class="num">Skor KPI</th><th class="num">Insentif</th><th>Konfirmasi</th><th></th></tr></thead>
            <tbody class="divide-y divide-slate-100">
            @forelse ($scores as $item)
                @php $s = $item['model']; @endphp
                <tr>
                    <td><div class="font-semibold text-slate-900">{{ $s->employee->full_name }}</div><div class="text-xs text-slate-500">{{ $s->employee->nik }}</div></td>
                    <td class="text-sm">{{ $s->employee->position }} · {{ $s->employee->department }}</td>
                    <td class="num font-semibold">{{ rtrim(rtrim(number_format($s->score, 2, ',', '.'), '0'), ',') }}</td>
                    <td class="num">{{ Money::format($item['incentive']) }}</td>
                    <td class="text-xs">
                        @if ($s->confirmed_at)
                            <span class="badge badge-published">Dikonfirmasi</span>
                            <div class="mt-0.5 text-slate-500">{{ $s->confirmer?->name }} · {{ $s->confirmed_at->format('d/m/Y') }}</div>
                        @else
                            <span class="badge badge-draft">Menunggu</span>
                        @endif
                    </td>
                    <td class="text-right">
                        @unless ($s->confirmed_at || $s->employee_id === auth()->user()->employee_id)
                            <form method="POST" action="{{ route('supervisor.kpi.confirm', $s) }}">
                                @csrf
                                <button class="btn btn-primary btn-sm">Konfirmasi</button>
                            </form>
                        @endunless
                    </td>
                </tr>
            @empty
                <tr><td colspan="6" class="py-10 text-center text-slate-500">Tidak ada skor KPI anggota tim pada periode ini.</td></tr>
            @endforelse
            </tbody>
        </table>
    </div>
</x-layouts.app>
