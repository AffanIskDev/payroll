<x-layouts.app title="Pengaturan Payroll">
    <h1 class="text-2xl font-bold text-slate-900">Pengaturan Payroll</h1>
    <p class="mt-1 text-sm text-slate-500">Parameter regulasi (UMK, plafon BPJS) wajib diperbarui setiap tahun. Perubahan berlaku untuk generate / hitung ulang slip draft berikutnya; slip yang sudah dikunci tidak berubah.</p>

    <form method="POST" action="{{ route('hr-manager.payroll.settings.update') }}" class="card mt-6 divide-y divide-slate-100">
        @csrf
        @method('PUT')
        @foreach ($definitions as $key => $def)
            <div class="grid gap-3 px-5 py-4 md:grid-cols-3 md:items-center">
                <div>
                    <label for="cfg_{{ $key }}" class="text-sm font-semibold text-slate-800">{{ $def['label'] }}</label>
                    <p class="text-xs text-slate-500">{{ $def['description'] }}</p>
                    <p class="font-mono text-[11px] text-slate-400">{{ $key }}@if (isset($updatedAt[$key])) · diubah {{ $updatedAt[$key]?->format('d/m/Y H:i') }}@endif</p>
                </div>
                <div class="md:col-span-2">
                    @php $value = old("configs.$key", $values[$key] ?? $def['default']); @endphp
                    @if ($def['type'] === 'enum')
                        <select id="cfg_{{ $key }}" name="configs[{{ $key }}]" class="input max-w-xs">
                            @foreach ($def['options'] as $optValue => $optLabel)
                                <option value="{{ $optValue }}" @selected($value === $optValue)>{{ $optLabel }}</option>
                            @endforeach
                        </select>
                    @elseif ($def['type'] === 'json')
                        <textarea id="cfg_{{ $key }}" name="configs[{{ $key }}]" rows="2" class="input font-mono text-xs">{{ $value }}</textarea>
                    @elseif (in_array($def['type'], ['money', 'int'], true))
                        <div class="relative max-w-xs">
                            @if ($def['type'] === 'money')<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs font-semibold text-slate-400">Rp</span>@endif
                            <input id="cfg_{{ $key }}" type="number" min="0" name="configs[{{ $key }}]" value="{{ $value }}" @class(['input text-right tabular-nums', 'pl-9' => $def['type'] === 'money'])>
                        </div>
                    @else
                        <input id="cfg_{{ $key }}" name="configs[{{ $key }}]" value="{{ $value }}" class="input">
                    @endif
                    @error("configs.$key")<p class="field-error">{{ $message }}</p>@enderror
                </div>
            </div>
        @endforeach
        <div class="flex justify-end px-5 py-4">
            <button class="btn btn-primary">Simpan Pengaturan</button>
        </div>
    </form>
</x-layouts.app>
