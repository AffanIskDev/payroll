<div @if ($active) wire:poll.2s @endif>
    @if ($period->isGenerating())
        @php $pct = $period->generation_total > 0 ? min(100, intdiv($period->generation_processed * 100, $period->generation_total)) : 0; @endphp
        <div class="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
            <div class="flex items-center justify-between text-sm font-semibold text-blue-900">
                <span>{{ $period->generation_status === 'queued' ? 'Menunggu antrean…' : 'Menghitung payroll…' }}</span>
                <span>{{ $period->generation_processed }} / {{ $period->generation_total ?: '?' }} karyawan</span>
            </div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-blue-100">
                <div class="h-full rounded-full bg-blue-600 transition-all" style="width: {{ $pct }}%"></div>
            </div>
            @if ($period->generation_status === 'queued')
                <p class="mt-2 text-xs text-blue-800">Pastikan queue worker berjalan (<code>php8.3 artisan queue:work</code>).</p>
            @endif
        </div>
    @elseif ($locked > 0)
        @php $total = $locked + $published; $pct = $total ? intdiv($published * 100, $total) : 0; @endphp
        <div class="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
            <div class="flex items-center justify-between text-sm font-semibold text-sky-900">
                <span>Membuat PDF ber-password &amp; menerbitkan ke Rumatku…</span>
                <span>{{ $published }} / {{ $total }} terbit</span>
            </div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-sky-100">
                <div class="h-full rounded-full bg-sky-600 transition-all" style="width: {{ $pct }}%"></div>
            </div>
        </div>
    @elseif ($period->generation_status === 'failed')
        <div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <span class="font-semibold">Generate gagal:</span> {{ $period->generation_error }}
        </div>
    @endif
</div>
