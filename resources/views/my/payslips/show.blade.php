@php use App\Support\Money; @endphp
<x-layouts.app :title="'Slip '.$payslip->period->period_name">
    <div class="mx-auto max-w-3xl">
        <nav class="text-sm text-slate-500"><a href="{{ route('my.payslips') }}" class="hover:text-brand-700">Slip Gaji</a> / <span class="text-slate-700">{{ $payslip->period->period_name }}</span></nav>
        <div class="mt-1 flex flex-wrap items-center justify-between gap-3">
            <h1 class="text-2xl font-bold text-slate-900">Slip Gaji {{ $payslip->period->period_name }}</h1>
            <a href="{{ route('my.payslips.download', $payslip) }}" target="_blank" class="btn btn-primary">Unduh PDF (password DDMMYY)</a>
        </div>

        <div class="card mt-5 bg-ink p-5 text-white">
            <div class="text-xs font-bold tracking-widest text-slate-400 uppercase">Take Home Pay</div>
            <div class="mt-1 text-3xl font-bold text-sky-400 tabular-nums">{{ Money::rupiah($slip['thp']) }}</div>
            <div class="mt-1 text-sm text-slate-300 italic">“{{ $slip['terbilang'] }}”</div>
            <div class="mt-3 text-xs text-slate-400">{{ $slip['bank_label'] }} · a.n. {{ $slip['account_name'] }} · dibayar {{ $slip['payment_date'] }}</div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            @foreach ($slip['stats'] as [$label, $value])
                <div class="rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-2.5 text-center">
                    <div class="text-[10px] font-bold tracking-wide text-blue-700 uppercase">{{ $label }}</div>
                    <div class="text-sm font-bold text-blue-950">{{ $value }}</div>
                </div>
            @endforeach
        </div>

        @foreach ([['Penerimaan', $slip['earnings'], $slip['gross'], 'text-emerald-700'], ['Potongan', $slip['deductions'], $slip['total_deductions'], 'text-red-700']] as [$title, $rows, $total, $color])
            <section class="card mt-4">
                <div class="card-header"><h2 class="card-title">{{ $title }}</h2></div>
                <div class="divide-y divide-slate-100">
                    @foreach ($rows as $row)
                        <div class="flex items-start justify-between gap-4 px-5 py-2.5">
                            <div><div class="text-sm font-medium text-slate-900">{{ $row['label'] }}</div><div class="text-xs text-slate-500">{{ $row['caption'] }}</div></div>
                            <div class="text-sm font-semibold tabular-nums">{{ Money::format($row['amount']) }}</div>
                        </div>
                    @endforeach
                </div>
                <div class="flex justify-between border-t border-slate-200 bg-slate-50 px-5 py-3 text-sm font-bold"><span>Total {{ strtolower($title) }}</span><span class="{{ $color }} tabular-nums">{{ Money::rupiah($total) }}</span></div>
            </section>
        @endforeach
    </div>
</x-layouts.app>
