<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Masuk · ROSY Payroll</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="min-h-screen bg-slate-100">
<div class="grid min-h-screen lg:grid-cols-2">
    <section class="hidden flex-col justify-between bg-ink p-10 text-slate-200 lg:flex">
        <div class="flex items-center gap-3">
            <svg class="size-8 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>
            <span class="text-xl font-bold text-white">ROSY | RUMATKU HRIS</span>
        </div>
        <div class="max-w-md">
            <h1 class="text-3xl leading-tight font-bold text-white">Payroll terpadu, dari presensi Rumatku sampai slip ber-password.</h1>
            <ul class="mt-6 space-y-3 text-sm text-slate-300">
                <li class="flex gap-3"><span class="mt-1 size-2 shrink-0 rounded-full bg-sky-400"></span>Penalti keterlambatan non-duplikasi (Rule A/B/C, basis 25 hari)</li>
                <li class="flex gap-3"><span class="mt-1 size-2 shrink-0 rounded-full bg-sky-400"></span>BPJS Full Gross dengan floor UMK Kabupaten Bekasi</li>
                <li class="flex gap-3"><span class="mt-1 size-2 shrink-0 rounded-full bg-sky-400"></span>PPh 21 TER bulanan + rekonsiliasi Pasal 17 di masa terakhir</li>
                <li class="flex gap-3"><span class="mt-1 size-2 shrink-0 rounded-full bg-sky-400"></span>Slip PDF terenkripsi AES, password tanggal lahir DDMMYY</li>
            </ul>
        </div>
        <p class="text-xs text-slate-500">Prototipe lokal dari PRD Modul Payroll ROSY × Rumatku v1.0.0</p>
    </section>

    <section class="flex items-center justify-center p-6">
        <div class="w-full max-w-sm">
            <div class="mb-6 lg:hidden">
                <span class="text-lg font-bold text-ink">ROSY | RUMATKU HRIS</span>
            </div>
            <div class="card p-6">
                <h2 class="text-lg font-bold text-slate-900">Masuk</h2>
                <p class="mt-1 text-sm text-slate-500">Gunakan akun ROSY Anda.</p>

                <form method="POST" action="{{ url('/login') }}" class="mt-5 space-y-4">
                    @csrf
                    <div>
                        <label class="label" for="email">Email</label>
                        <input id="email" name="email" type="email" value="{{ old('email') }}" required autofocus autocomplete="username" @class(['input', 'input-error' => $errors->has('email')])>
                        @error('email')<p class="field-error">{{ $message }}</p>@enderror
                    </div>
                    <div>
                        <label class="label" for="password">Password</label>
                        <input id="password" name="password" type="password" required autocomplete="current-password" class="input">
                    </div>
                    <label class="flex items-center gap-2 text-sm text-slate-600">
                        <input type="checkbox" name="remember" class="rounded border-slate-300"> Ingat saya
                    </label>
                    <button type="submit" class="btn btn-primary w-full">Masuk</button>
                </form>
            </div>

            @if ($demoAccounts->isNotEmpty())
                <div class="card mt-4 p-4">
                    <div class="text-xs font-bold tracking-wide text-slate-500 uppercase">Akun demo (lokal) · password: <code class="rounded bg-slate-100 px-1 text-slate-700">password</code></div>
                    <ul class="mt-2 divide-y divide-slate-100">
                        @foreach ($demoAccounts as $account)
                            <li class="flex items-center justify-between gap-2 py-2">
                                <div class="min-w-0">
                                    <div class="truncate text-sm font-semibold text-slate-800">{{ $account->name }}</div>
                                    <div class="truncate text-xs text-slate-500">{{ $account->email }}</div>
                                </div>
                                <button type="button" class="btn btn-secondary btn-sm shrink-0"
                                        onclick="document.getElementById('email').value='{{ $account->email }}';document.getElementById('password').value='password';document.getElementById('password').form.requestSubmit();">
                                    {{ $account->roleLabel() }}
                                </button>
                            </li>
                        @endforeach
                    </ul>
                </div>
            @endif
        </div>
    </section>
</div>
</body>
</html>
