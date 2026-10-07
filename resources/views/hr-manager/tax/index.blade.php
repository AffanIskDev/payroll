@php use App\Support\Money; @endphp
<x-layouts.app :title="'Bukti Potong 1721-A1 '.$year">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Bukti Potong PPh 21 · Formulir 1721-A1</h1>
            <p class="mt-1 max-w-2xl text-sm text-slate-500">Rekap setahun dari saldo awal YTD + slip final. Ini dokumen pendamping internal; bukti potong resmi tetap diterbitkan lewat Coretax DJP.</p>
        </div>
        <div class="flex items-center gap-2">
            <form method="GET" onchange="window.location = '{{ url('/hr-manager/tax/1721-a1') }}/' + this.year.value">
                <select name="year" class="input w-32">
                    @foreach ($years as $y)<option value="{{ $y }}" @selected($y === $year)>{{ $y }}</option>@endforeach
                </select>
            </form>
            @if ($reports->isNotEmpty())
                <a href="{{ route('hr-manager.tax.zip', $year) }}" class="btn btn-primary">Unduh ZIP semua karyawan</a>
            @endif
        </div>
    </div>

    <div class="card mt-6 overflow-x-auto">
        <table class="table-base">
            <thead>
            <tr>
                <th>Karyawan</th><th>Masa</th><th class="num">Bruto Setahun (8)</th><th class="num">Neto (13)</th>
                <th class="num">PKP (17)</th><th class="num">PPh Setahun (18)</th><th class="num">Kurang/(Lebih) Masa Akhir (22)</th><th>Status</th><th></th>
            </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            @forelse ($reports as $item)
                @php $r = $item['report']; @endphp
                <tr>
                    <td><div class="font-semibold text-slate-900">{{ $item['employee']->full_name }}</div><div class="text-xs text-slate-500">{{ $item['employee']->nik }} · {{ $r['employee']['ptkp_status'] ?? $item['employee']->ptkp_status }}</div></td>
                    @if ($r)
                        <td>{{ sprintf('%02d', $r['period_from']) }}–{{ sprintf('%02d', $r['period_to']) }} <span class="text-xs text-slate-500">({{ $r['months_worked'] }} bln)</span></td>
                        <td class="num">{{ Money::format($r['lines'][8]) }}</td>
                        <td class="num">{{ Money::format($r['lines'][13]) }}</td>
                        <td class="num">{{ Money::format($r['lines'][17]) }}</td>
                        <td class="num">{{ Money::format($r['lines'][18]) }}</td>
                        @if ($r['is_final'])
                            <td @class(['num font-semibold', 'text-red-700' => $r['lines'][22] > 0, 'text-emerald-700' => $r['lines'][22] < 0])>{{ Money::format($r['lines'][22]) }}</td>
                        @else
                            <td class="num text-xs text-slate-400 italic" title="Proyeksi bila tahun pajak ditutup dengan data saat ini">{{ Money::format($r['lines'][22]) }} (proyeksi)</td>
                        @endif
                        <td>
                            @if ($r['is_final'])<span class="badge badge-published">Final</span>
                            @else<span class="badge badge-draft" title="Masa pajak terakhir belum diproses">Sementara</span>@endif
                        </td>
                        <td class="text-right"><a href="{{ route('hr-manager.tax.download', [$year, $item['employee']]) }}" target="_blank" class="btn btn-secondary btn-sm">PDF</a></td>
                    @else
                        <td colspan="8" class="text-xs text-slate-500">{{ $item['error'] }}</td>
                    @endif
                </tr>
            @empty
                <tr><td colspan="9" class="py-10 text-center text-slate-500">Belum ada data pajak untuk tahun {{ $year }}.</td></tr>
            @endforelse
            </tbody>
        </table>
    </div>
    <p class="mt-3 text-xs text-slate-500">“Sementara” = masa pajak terakhir (Desember / bulan berhenti bekerja) belum diproses, sehingga baris 22 adalah proyeksi kurang/lebih potong bila tahun pajak ditutup dengan data saat ini.</p>
</x-layouts.app>
