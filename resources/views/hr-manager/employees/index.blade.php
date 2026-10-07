@php use App\Support\Money; @endphp
<x-layouts.app title="Karyawan & Gaji">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Karyawan &amp; Profil Gaji</h1>
            <p class="mt-1 text-sm text-slate-500">Master gaji pokok, tunjangan, checklist BPJS, dan rekening tujuan transfer. Di produksi data ini disinkronkan dari ROSY.</p>
        </div>
        <form method="GET"><input type="search" name="q" value="{{ $search }}" placeholder="Cari nama, NIK, divisi…" class="input w-64"></form>
    </div>

    <div class="card mt-6 overflow-x-auto">
        <table class="table-base">
            <thead>
            <tr>
                <th>Karyawan</th><th>Divisi / Jabatan</th><th>PTKP</th><th class="num">Gaji Pokok</th><th class="num">Tunj. Jabatan</th>
                <th class="num">Tunj. Kehadiran</th><th>BPJS</th><th>Rekening</th><th></th>
            </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            @foreach ($employees as $e)
                @php $p = $e->salaryProfile; @endphp
                <tr>
                    <td>
                        <div class="font-semibold text-slate-900">{{ $e->full_name }}</div>
                        <div class="text-xs text-slate-500">{{ $e->nik }} · lahir {{ $e->birth_date->format('d/m/Y') }}
                            @if ($e->is_management)<span class="badge badge-muted ml-1">manajemen</span>@endif
                            @unless ($e->is_active)<span class="badge bg-red-50 text-red-700 ml-1">nonaktif</span>@endunless
                        </div>
                    </td>
                    <td class="whitespace-normal"><div>{{ $e->department }}</div><div class="text-xs text-slate-500">{{ $e->position }} · {{ $e->employment_status }}</div></td>
                    <td>{{ $e->ptkp_status }}</td>
                    @if ($p)
                        <td class="num">{{ Money::format($p->basic_salary) }}</td>
                        <td class="num">{{ Money::format($p->position_allowance) }}</td>
                        <td class="num">{{ Money::format($p->monthly_attendance_allowance) }}</td>
                        <td class="whitespace-normal text-xs"><div class="flex max-w-[8.5rem] flex-wrap gap-1">
                            @foreach (['has_bpjs_kes' => 'Kes', 'has_jkk' => 'JKK', 'has_jkm' => 'JKM', 'has_jht' => 'JHT', 'has_jp' => 'JP'] as $flag => $label)
                                <span @class(['badge', 'bg-emerald-50 text-emerald-700' => $p->{$flag}, 'bg-slate-100 text-slate-400 line-through' => ! $p->{$flag}])>{{ $label }}</span>
                            @endforeach
                        </div></td>
                        <td class="text-xs">{{ $p->bank_name }} · {{ $p->bank_account_number }}</td>
                    @else
                        <td colspan="5" class="text-center text-xs text-amber-700">Belum punya profil gaji — tidak ikut payroll</td>
                    @endif
                    <td class="text-right"><a href="{{ route('hr-manager.employees.edit', $e) }}" class="btn btn-secondary btn-sm">Ubah</a></td>
                </tr>
            @endforeach
            </tbody>
        </table>
    </div>
</x-layouts.app>
