@php use App\Support\Money; @endphp
<x-layouts.app title="Impor Saldo Awal Pajak YTD">
    <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
            <h1 class="text-2xl font-bold text-slate-900">Impor Saldo Awal Pajak (YTD)</h1>
            <p class="mt-1 max-w-2xl text-sm text-slate-500">Akumulasi bruto, iuran JHT+JP pekerja, biaya jabatan, dan PPh 21 dari sistem lama sejak Januari. Dipakai rekonsiliasi PPh 21 Desember (Pasal 17) dan Formulir 1721-A1.</p>
        </div>
        <a href="{{ route('hr-manager.payroll.import-ytd.template') }}" class="btn btn-secondary">Unduh template .xlsx</a>
    </div>

    <div class="mt-6 grid gap-5 lg:grid-cols-3">
        <form method="POST" action="{{ route('hr-manager.payroll.import-ytd.validate') }}" enctype="multipart/form-data" class="card space-y-4 p-5">
            @csrf
            <div>
                <div class="text-sm font-bold text-slate-800">Langkah 1 · Unggah &amp; validasi</div>
                <p class="mt-1 text-xs text-slate-500">Belum ada data yang disimpan pada langkah ini.</p>
            </div>
            <input type="file" name="file" accept=".xlsx,.xls,.csv" required class="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-semibold file:text-brand-700 hover:file:bg-brand-100">
            @error('file')<p class="field-error">{{ $message }}</p>@enderror
            <button class="btn btn-primary w-full">Validasi Format</button>
            <div class="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                <div class="font-semibold text-slate-700">Urutan kolom (baris 1 = judul):</div>
                <ol class="mt-1 list-decimal space-y-0.5 pl-4">
                    <li>employee_id / NIK (wajib ada di master ROSY)</li>
                    <li>tax_year (YYYY)</li>
                    <li>cutoff_month (1–11)</li>
                    <li>ptkp_status (TK/0 … K/3)</li>
                    <li>gross_income_ytd</li>
                    <li>employee_jht_jp_ytd</li>
                    <li>biaya_jabatan_ytd</li>
                    <li>pph21_paid_ytd</li>
                    <li>notes (opsional)</li>
                </ol>
                <p class="mt-2">Juga bisa lewat terminal: <code class="rounded bg-white px-1">php8.3 artisan payroll:import-ytd file.xlsx</code></p>
            </div>
        </form>

        <div class="space-y-5 lg:col-span-2">
            @if ($result)
                <section class="card">
                    <div class="card-header">
                        <h2 class="card-title">Hasil validasi · {{ $result['file'] }}</h2>
                        <span class="text-sm text-slate-600">{{ $result['total'] }} baris · <span class="font-semibold text-emerald-700">{{ count($result['valid']) }} lolos</span> · <span class="font-semibold text-red-700">{{ count($result['errors']) }} gagal</span></span>
                    </div>
                    @if ($result['errors'])
                        <div class="border-b border-red-100 bg-red-50/60 px-5 py-3">
                            <div class="text-sm font-semibold text-red-800">Perbaiki baris berikut lalu unggah ulang (data saldo pajak disimpan semua-atau-tidak-sama-sekali):</div>
                            <ul class="mt-2 space-y-1 text-sm text-red-800">
                                @foreach ($result['errors'] as $error)
                                    <li><span class="font-mono text-xs">Baris {{ $error['row'] }}</span> · {{ $error['nik'] ?: '(NIK kosong)' }} — {{ implode(' ', $error['messages']) }}</li>
                                @endforeach
                            </ul>
                        </div>
                    @endif
                    @foreach ($result['warnings'] as $w)
                        <div class="border-b border-amber-100 bg-amber-50 px-5 py-2 text-xs text-amber-800">Baris {{ $w['row'] }} ({{ $w['nik'] }}): {{ $w['message'] }}</div>
                    @endforeach
                    @if ($result['valid'])
                        <div class="overflow-x-auto">
                            <table class="table-base">
                                <thead><tr><th>Baris</th><th>NIK</th><th>Tahun</th><th>s/d Bulan</th><th>PTKP</th><th class="num">Bruto YTD</th><th class="num">JHT+JP</th><th class="num">B. Jabatan</th><th class="num">PPh 21</th></tr></thead>
                                <tbody class="divide-y divide-slate-100">
                                @foreach ($result['valid'] as $row)
                                    <tr>
                                        <td class="font-mono text-xs">{{ $row['row'] }}</td>
                                        <td>{{ $row['nik'] }}</td>
                                        <td>{{ $row['tax_year'] }}</td>
                                        <td>{{ $row['cutoff_month'] }}</td>
                                        <td>{{ $row['ptkp_status'] }}</td>
                                        <td class="num">{{ Money::format($row['gross_income_ytd']) }}</td>
                                        <td class="num">{{ Money::format($row['employee_jht_jp_ytd']) }}</td>
                                        <td class="num">{{ Money::format($row['biaya_jabatan_ytd']) }}</td>
                                        <td class="num">{{ Money::format($row['pph21_paid_ytd']) }}</td>
                                    </tr>
                                @endforeach
                                </tbody>
                            </table>
                        </div>
                    @endif
                    <div class="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3">
                        <span class="text-xs text-slate-500">Langkah 2 · Simpan (updateOrCreate per NIK + tahun pajak)</span>
                        <form method="POST" action="{{ route('hr-manager.payroll.import-ytd.commit') }}">
                            @csrf
                            <button class="btn btn-success" @disabled(! $result['can_commit'])>Simpan {{ count($result['valid']) }} saldo awal</button>
                        </form>
                    </div>
                </section>
            @endif

            <section class="card">
                <div class="card-header"><h2 class="card-title">Saldo awal tersimpan</h2><span class="text-sm text-slate-500">{{ $balances->count() }} karyawan</span></div>
                <div class="overflow-x-auto">
                    <table class="table-base">
                        <thead><tr><th>Karyawan</th><th>Tahun</th><th>s/d Bulan</th><th>PTKP</th><th class="num">Bruto YTD</th><th class="num">JHT+JP</th><th class="num">PPh 21</th><th>Catatan</th></tr></thead>
                        <tbody class="divide-y divide-slate-100">
                        @forelse ($balances as $b)
                            <tr>
                                <td><div class="font-medium">{{ $b->employee->full_name }}</div><div class="text-xs text-slate-500">{{ $b->employee->nik }}</div></td>
                                <td>{{ $b->tax_year }}</td>
                                <td>{{ \App\Support\Tanggal::BULAN[$b->cutoff_month] }}</td>
                                <td>{{ $b->ptkp_status }}</td>
                                <td class="num">{{ Money::format($b->gross_income_ytd) }}</td>
                                <td class="num">{{ Money::format($b->employee_jht_jp_ytd) }}</td>
                                <td class="num">{{ Money::format($b->pph21_paid_ytd) }}</td>
                                <td class="max-w-[10rem] truncate text-xs text-slate-500" title="{{ $b->notes }}">{{ $b->notes }}</td>
                            </tr>
                        @empty
                            <tr><td colspan="8" class="py-8 text-center text-slate-500">Belum ada saldo awal.</td></tr>
                        @endforelse
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    </div>
</x-layouts.app>
