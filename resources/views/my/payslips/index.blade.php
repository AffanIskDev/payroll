@php use App\Support\Money; @endphp
<x-layouts.app title="Slip Gaji Saya">
    <div class="mx-auto max-w-3xl">
        <h1 class="text-2xl font-bold text-slate-900">Slip Gaji</h1>
        <p class="mt-1 text-sm text-slate-500">Sama dengan menu “Slip Gaji” di aplikasi Rumatku. File PDF dilindungi password <b>tanggal lahir 6 digit (DDMMYY)</b>, mis. lahir 15 Maret 1990 → <code class="rounded bg-slate-100 px-1">150390</code>.</p>

        @if ($notifications->whereNull('read_at')->isNotEmpty())
            <div class="card mt-5 border-blue-200 bg-blue-50/60">
                <div class="flex items-center justify-between px-5 py-3">
                    <span class="text-sm font-bold text-blue-900">Notifikasi baru</span>
                    <form method="POST" action="{{ route('my.notifications.read') }}">@csrf<button class="text-xs font-semibold text-blue-700 hover:underline">Tandai sudah dibaca</button></form>
                </div>
                @foreach ($notifications->whereNull('read_at') as $n)
                    <a href="{{ route('my.payslips.show', $n->data['payslip_id']) }}" class="block border-t border-blue-100 px-5 py-2.5 hover:bg-blue-50">
                        <div class="text-sm font-semibold text-slate-900">{{ $n->data['title'] }}</div>
                        <div class="text-xs text-slate-600">{{ $n->data['body'] }} · {{ $n->created_at->diffForHumans() }}</div>
                    </a>
                @endforeach
            </div>
        @endif

        <div class="mt-5 space-y-3">
            @forelse ($payslips as $slip)
                <div class="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                    <div>
                        <div class="text-base font-bold text-slate-900">{{ $slip->period->period_name }}</div>
                        <div class="text-xs text-slate-500">Dibayar {{ \App\Support\Tanggal::panjang($slip->period->payment_date) }} · {{ \App\Support\BankDirectory::label($slip->bank_name) }} {{ $slip->bank_account_number }}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-xs font-semibold tracking-wide text-slate-500 uppercase">Take home pay</div>
                        <div class="text-lg font-bold text-emerald-700 tabular-nums">{{ Money::rupiah($slip->take_home_pay) }}</div>
                    </div>
                    <div class="flex gap-2">
                        <a href="{{ route('my.payslips.show', $slip) }}" class="btn btn-secondary btn-sm">Rincian</a>
                        <a href="{{ route('my.payslips.download', $slip) }}" target="_blank" class="btn btn-primary btn-sm">Unduh PDF</a>
                    </div>
                </div>
            @empty
                <div class="card px-5 py-10 text-center text-sm text-slate-500">Belum ada slip gaji yang terbit.</div>
            @endforelse
        </div>
    </div>
</x-layouts.app>
