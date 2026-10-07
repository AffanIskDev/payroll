@php use App\Support\Money; @endphp
<x-layouts.app :title="'Profil Gaji · '.$employee->full_name">
    <nav class="text-sm text-slate-500"><a href="{{ route('hr-manager.employees.index') }}" class="hover:text-brand-700">Karyawan &amp; Gaji</a> / <span class="text-slate-700">{{ $employee->full_name }}</span></nav>
    <h1 class="mt-1 text-2xl font-bold text-slate-900">Profil Gaji · {{ $employee->full_name }}</h1>
    <p class="mt-1 text-sm text-slate-500">{{ $employee->nik }} · {{ $employee->position }} · {{ $employee->department }}</p>

    <form method="POST" action="{{ route('hr-manager.employees.update', $employee) }}" class="mt-6 grid gap-5 lg:grid-cols-3">
        @csrf
        @method('PUT')
        <section class="card space-y-4 p-5 lg:col-span-2">
            <h2 class="card-title">Komponen gaji</h2>
            <div class="grid gap-4 sm:grid-cols-2">
                @foreach ([
                    'basic_salary' => 'Gaji pokok',
                    'position_allowance' => 'Tunjangan jabatan (tetap)',
                    'monthly_attendance_allowance' => 'Tunjangan kehadiran (penuh 25 hari)',
                    'overtime_hourly_rate' => 'Tarif lembur flat per jam',
                ] as $field => $label)
                    <div>
                        <label class="label" for="{{ $field }}">{{ $label }}</label>
                        <div class="relative">
                            <span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs font-semibold text-slate-400">Rp</span>
                            <input id="{{ $field }}" type="number" min="0" name="{{ $field }}" value="{{ old($field, $profile->{$field} ?? 0) }}" @class(['input pl-9 text-right tabular-nums', 'input-error' => $errors->has($field)])>
                        </div>
                        @error($field)<p class="field-error">{{ $message }}</p>@enderror
                    </div>
                @endforeach
                <div>
                    <label class="label" for="ptkp_status">Status PTKP</label>
                    <select id="ptkp_status" name="ptkp_status" class="input">
                        @foreach (\App\Models\Employee::PTKP_STATUSES as $s)
                            <option value="{{ $s }}" @selected(old('ptkp_status', $employee->ptkp_status) === $s)>{{ $s }} — TER {{ \App\Services\Payroll\Pph21TerCalculatorService::CATEGORY[$s] }}</option>
                        @endforeach
                    </select>
                </div>
            </div>

            <h2 class="card-title pt-2">Rekening tujuan transfer</h2>
            <div class="grid gap-4 sm:grid-cols-3">
                <div>
                    <label class="label" for="bank_name">Bank</label>
                    <select id="bank_name" name="bank_name" class="input">
                        @foreach ($banks as $code => $label)
                            <option value="{{ $code }}" @selected(old('bank_name', $profile->bank_name) === $code)>{{ $label }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label class="label" for="bank_account_number">Nomor rekening</label>
                    <input id="bank_account_number" name="bank_account_number" value="{{ old('bank_account_number', $profile->bank_account_number) }}" class="input font-mono">
                    @error('bank_account_number')<p class="field-error">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label class="label" for="bank_account_name">Nama di rekening</label>
                    <input id="bank_account_name" name="bank_account_name" value="{{ old('bank_account_name', $profile->bank_account_name ?? mb_strtoupper($employee->full_name)) }}" class="input uppercase">
                </div>
            </div>
        </section>

        <section class="card space-y-4 p-5">
            <h2 class="card-title">Checklist BPJS</h2>
            <div class="space-y-2">
                @foreach (['has_bpjs_kes' => 'BPJS Kesehatan (4% + 1%)', 'has_jkk' => 'JKK — Jaminan Kecelakaan Kerja', 'has_jkm' => 'JKM — Jaminan Kematian (0,3%)', 'has_jht' => 'JHT — Jaminan Hari Tua (3,7% + 2%)', 'has_jp' => 'JP — Jaminan Pensiun (2% + 1%)'] as $flag => $label)
                    <label class="flex items-center gap-2 text-sm text-slate-700">
                        <input type="checkbox" name="{{ $flag }}" value="1" @checked(old($flag, $profile->{$flag})) class="rounded border-slate-300"> {{ $label }}
                    </label>
                @endforeach
            </div>
            <div>
                <label class="label" for="jkk_rate">Tingkat risiko JKK</label>
                <select id="jkk_rate" name="jkk_rate" class="input">
                    @foreach (['0.0024' => '0,24% — sangat rendah (default)', '0.0054' => '0,54% — rendah', '0.0089' => '0,89% — sedang', '0.0127' => '1,27% — tinggi', '0.0174' => '1,74% — sangat tinggi'] as $rate => $label)
                        <option value="{{ $rate }}" @selected(old('jkk_rate', $profile->jkk_rate) == $rate)>{{ $label }}</option>
                    @endforeach
                </select>
            </div>
            @if ($preview)
                <div class="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                    <div class="font-semibold text-slate-700">Simulasi tersimpan saat ini</div>
                    Basis Kes {{ Money::rupiah($preview['kes_base']) }}{{ $preview['umk_floor_applied'] ? ' (floor UMK)' : '' }} ·
                    tunjangan BPJS {{ Money::rupiah($preview['tunjangan_bpjs_kes'] + $preview['tunjangan_bpjs_tk']) }} ·
                    setoran total {{ Money::rupiah($preview['iuran_bpjs_kes_total'] + $preview['iuran_bpjs_tk_total']) }}
                </div>
            @endif
            <button class="btn btn-primary w-full">Simpan Profil</button>
        </section>
    </form>
</x-layouts.app>
