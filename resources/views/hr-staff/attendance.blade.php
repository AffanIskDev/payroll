@php use App\Support\Money; @endphp
<x-layouts.app title="Presensi & Potongan">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Draft Potongan Presensi</h1>
            <p class="mt-1 max-w-2xl text-sm text-slate-500">
                Tinjau penalti keterlambatan non-duplikasi (Rule A/B/C, ambil tertinggi) dan ketidakhadiran dari data Rumatku. Read-only.
                @unless ($canSeeManagement) Data karyawan level manajemen tidak ditampilkan. @endunless
            </p>
        </div>
        @if ($periods->isNotEmpty())
            <form method="GET" onchange="window.location = '{{ url('/hr-staff/attendance') }}/' + this.period.value">
                <select name="period" class="input w-56">
                    @foreach ($periods as $p)<option value="{{ $p->id }}" @selected($period && $p->id === $period->id)>{{ $p->period_name }} · {{ $p->status }}</option>@endforeach
                </select>
            </form>
        @endif
    </div>

    <div class="mt-4 grid gap-3 text-xs text-slate-600 sm:grid-cols-3">
        <div class="card px-4 py-3"><b class="text-slate-800">Rule A</b> · terlambat ≥ 60 menit dalam sehari = 1 hari penalti</div>
        <div class="card px-4 py-3"><b class="text-slate-800">Rule B</b> · setiap 3× terlambat ≥ 15 menit = 1 hari penalti</div>
        <div class="card px-4 py-3"><b class="text-slate-800">Rule C</b> · setiap kelipatan 60 menit akumulasi = 1 hari penalti</div>
    </div>

    <div class="card mt-4 overflow-x-auto">
        <table class="table-base">
            <thead>
            <tr>
                <th>Karyawan</th><th class="num">Hadir</th><th class="num">Izin/Sakit/Cuti</th><th class="num">Alpa</th>
                <th class="num">Σ Menit Telat</th><th class="num">≥15 mnt</th><th class="num">≥60 mnt</th>
                <th class="num">A / B / C</th><th class="num">Penalti</th><th class="num">Potongan</th><th>Status slip</th>
            </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            @forelse ($rows as $row)
                @php $l = $row->system_values['late'] ?? []; @endphp
                <tr>
                    <td><div class="font-semibold text-slate-900">{{ $row->employee_name }}</div><div class="text-xs text-slate-500">{{ $row->employee_nik }} · {{ $row->department }}</div></td>
                    <td class="num">{{ $row->attended_days }}</td>
                    <td class="num">{{ $row->leave_sick_days }}</td>
                    <td @class(['num', 'font-semibold text-red-700' => $row->absent_days > 0])>{{ $row->absent_days }}</td>
                    <td class="num">{{ $row->late_minutes_total }}</td>
                    <td class="num">{{ $row->late_count_15 }}</td>
                    <td class="num">{{ $row->late_days_60 }}</td>
                    <td class="num text-xs">{{ $l['rule_a_days'] ?? 0 }} / {{ $l['rule_b_days'] ?? 0 }} / {{ $l['rule_c_days'] ?? 0 }}</td>
                    <td class="num font-semibold">{{ $row->late_penalty_days ? $row->late_penalty_days.' hari' : '–' }}</td>
                    <td class="num text-red-700">{{ $row->late_penalty_amount ? Money::format($row->late_penalty_amount) : '–' }}</td>
                    <td><x-status-badge :status="$row->status" /></td>
                </tr>
            @empty
                <tr><td colspan="11" class="py-10 text-center text-slate-500">Belum ada data slip untuk periode ini.</td></tr>
            @endforelse
            </tbody>
        </table>
    </div>
</x-layouts.app>
