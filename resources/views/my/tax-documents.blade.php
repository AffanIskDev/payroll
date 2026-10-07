@php use App\Support\Money; @endphp
<x-layouts.app title="Bukti Potong Saya">
    <div class="mx-auto max-w-3xl">
        <h1 class="text-2xl font-bold text-slate-900">Bukti Potong PPh 21 (1721-A1)</h1>
        <p class="mt-1 text-sm text-slate-500">Untuk lapor SPT Tahunan. PDF dilindungi password tanggal lahir (DDMMYY). Dokumen resmi tetap mengacu pada bukti potong dari Coretax DJP.</p>

        @foreach ($pendingYears as $pending)
            <div class="card mt-5 border-amber-200 bg-amber-50/60 px-5 py-4 text-sm text-amber-900">
                Bukti potong tahun pajak <b>{{ $pending }}</b> belum final. Dokumen terbit setelah masa pajak Desember (atau bulan berhenti bekerja) diproses HRD.
            </div>
        @endforeach

        <div class="mt-5 space-y-3">
            @forelse ($documents as $doc)
                @php $r = $doc['report']; @endphp
                <div class="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                    <div>
                        <div class="text-base font-bold text-slate-900">Tahun Pajak {{ $doc['year'] }} <span class="badge badge-published ml-1">Final</span></div>
                        <div class="text-xs text-slate-500">Masa {{ sprintf('%02d', $r['period_from']) }}–{{ sprintf('%02d', $r['period_to']) }} · bruto {{ Money::rupiah($r['lines'][8]) }} · PPh 21 setahun {{ Money::rupiah($r['lines'][18]) }}</div>
                    </div>
                    <a href="{{ route('my.tax-documents.download', $doc['year']) }}" target="_blank" class="btn btn-primary btn-sm">Unduh PDF</a>
                </div>
            @empty
                <div class="card px-5 py-10 text-center text-sm text-slate-500">Belum ada bukti potong final.</div>
            @endforelse
        </div>
    </div>
</x-layouts.app>
