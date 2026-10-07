@props(['title' => null])
@php
    use App\Models\User;
    $user = auth()->user();
    $unread = $user?->employee_id ? $user->unreadNotifications()->count() : 0;
    // [label, href, pola route aktif] atau [label, null, pola, [submenu...]]
    $nav = [];
    if ($user?->isManagerHrd()) {
        $nav = [
            ['Payroll', route('hr-manager.payroll.index'), 'hr-manager.payroll.index|hr-manager.payroll.show|hr-manager.payroll.workbench'],
            ['Karyawan', route('hr-manager.employees.index'), 'hr-manager.employees.*'],
            ['Presensi', route('hr-staff.attendance'), 'hr-staff.*'],
            ['KPI Tim', route('supervisor.kpi'), 'supervisor.*'],
            ['Pajak', null, 'hr-manager.payroll.import-ytd*|hr-manager.tax.*', [
                ['Impor Saldo Awal YTD', route('hr-manager.payroll.import-ytd')],
                ['Bukti Potong 1721-A1', route('hr-manager.tax.index', ['year' => now()->year])],
            ]],
            ['Pengaturan', route('hr-manager.payroll.settings'), 'hr-manager.payroll.settings*'],
        ];
    } else {
        if ($user?->hasRole(User::ROLE_STAFF_HRD)) {
            $nav[] = ['Presensi & Potongan', route('hr-staff.attendance'), 'hr-staff.*'];
        }
        if ($user?->hasRole(User::ROLE_ATASAN_DIVISI)) {
            $nav[] = ['KPI Tim', route('supervisor.kpi'), 'supervisor.*'];
        }
        if ($user?->employee_id) {
            $nav[] = ['Slip Gaji', route('my.payslips'), 'my.payslips*'];
            $nav[] = ['Bukti Potong', route('my.tax-documents'), 'my.tax-documents*'];
        }
    }
    $personal = $user?->employee_id && $user->isManagerHrd()
        ? [['Slip Gaji Saya', route('my.payslips')], ['Bukti Potong Saya', route('my.tax-documents')]]
        : [];
    $isActive = fn (string $patterns) => collect(explode('|', $patterns))->contains(fn ($p) => request()->routeIs($p));
@endphp
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{{ $title ? $title.' · ' : '' }}ROSY Payroll</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%231e40af' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 10.5 12 3l9 7.5'/%3E%3Cpath d='M5 9.5V21h14V9.5'/%3E%3Cpath d='M9.5 21v-6h5v6'/%3E%3C/svg%3E">
    @vite(['resources/css/app.css', 'resources/js/app.js'])
    @livewireStyles
</head>
<body class="min-h-screen">
<div x-data="{ open: false }" class="flex min-h-screen flex-col">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div class="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
            <a href="{{ route('dashboard') }}" class="flex shrink-0 items-center gap-2">
                <svg class="size-6 text-brand-800" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>
                <span class="leading-tight">
                    <span class="block text-[15px] font-bold text-ink">ROSY | RUMATKU HRIS</span>
                    <span class="block text-[11px] font-medium tracking-wide text-slate-500 uppercase">Modul Payroll</span>
                </span>
            </a>

            <nav class="hidden flex-1 items-center gap-0.5 lg:flex">
                @foreach ($nav as $item)
                    @if (isset($item[3]))
                        <div class="relative" x-data="{ menu: false }" @click.outside="menu = false" @keydown.escape="menu = false">
                            <button type="button" @click="menu = !menu" @class(['nav-link inline-flex items-center gap-1 whitespace-nowrap', 'nav-link-active' => $isActive($item[2])])>
                                {{ $item[0] }}
                                <svg class="size-3.5" viewBox="0 0 20 20" fill="currentColor"><path d="M5.3 7.3a1 1 0 0 1 1.4 0L10 10.6l3.3-3.3a1 1 0 1 1 1.4 1.4l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 0-1.4z"/></svg>
                            </button>
                            <div x-cloak x-show="menu" x-transition class="absolute left-0 z-50 mt-1 w-56 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                                @foreach ($item[3] as [$subLabel, $subHref])
                                    <a href="{{ $subHref }}" class="block px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">{{ $subLabel }}</a>
                                @endforeach
                            </div>
                        </div>
                    @else
                        <a href="{{ $item[1] }}" @class(['nav-link whitespace-nowrap', 'nav-link-active' => $isActive($item[2])])>{{ $item[0] }}</a>
                    @endif
                @endforeach
            </nav>

            <div class="ml-auto flex items-center gap-2">
                @if ($user?->employee_id)
                    <a href="{{ route('my.payslips') }}" class="relative rounded-full p-2 text-slate-500 hover:bg-slate-100" title="Notifikasi slip gaji">
                        <svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
                        @if ($unread > 0)
                            <span class="absolute -top-0.5 -right-0.5 grid min-w-5 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">{{ $unread > 9 ? '9+' : $unread }}</span>
                        @endif
                    </a>
                @endif
                <div class="relative" x-data="{ menu: false }" @click.outside="menu = false" @keydown.escape="menu = false">
                    <button type="button" @click="menu = !menu" class="flex items-center gap-2 rounded-lg px-2 py-1 text-right leading-tight hover:bg-slate-100">
                        <span class="hidden sm:block">
                            <span class="block text-sm font-semibold text-slate-800">{{ $user?->name }}</span>
                            <span class="block text-[11px] font-medium text-slate-500">{{ $user?->roleLabel() }}</span>
                        </span>
                        <span class="grid size-8 place-items-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">{{ collect(explode(' ', (string) $user?->name))->map(fn ($w) => mb_substr($w, 0, 1))->take(2)->implode('') }}</span>
                    </button>
                    <div x-cloak x-show="menu" x-transition class="absolute right-0 z-50 mt-1 w-56 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                        <div class="border-b border-slate-100 px-3 py-2 text-xs text-slate-500">{{ $user?->email }}</div>
                        @foreach ($personal as [$label, $href])
                            <a href="{{ $href }}" class="block px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">{{ $label }}</a>
                        @endforeach
                        <form method="POST" action="{{ route('logout') }}">
                            @csrf
                            <button type="submit" class="block w-full px-3 py-2 text-left text-sm font-medium text-red-700 hover:bg-red-50">Keluar</button>
                        </form>
                    </div>
                </div>
                <button class="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden" @click="open = !open" aria-label="Menu">
                    <svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
                </button>
            </div>
        </div>
        <nav x-cloak x-show="open" x-transition class="border-t border-slate-100 px-4 py-2 lg:hidden">
            @foreach ($nav as $item)
                @if (isset($item[3]))
                    @foreach ($item[3] as [$subLabel, $subHref])
                        <a href="{{ $subHref }}" class="nav-link block">{{ $subLabel }}</a>
                    @endforeach
                @else
                    <a href="{{ $item[1] }}" @class(['nav-link block', 'nav-link-active' => $isActive($item[2])])>{{ $item[0] }}</a>
                @endif
            @endforeach
            @foreach ($personal as [$label, $href])
                <a href="{{ $href }}" class="nav-link block">{{ $label }}</a>
            @endforeach
        </nav>
    </header>

    <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        @if (session('status'))
            <div class="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{{ session('status') }}</div>
        @endif
        @if (session('error'))
            <div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">{{ session('error') }}</div>
        @endif
        @if ($errors->any() && ! ($hideErrorSummary ?? false))
            <div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                <div class="font-semibold">Periksa kembali isian berikut:</div>
                <ul class="mt-1 list-disc pl-5">
                    @foreach ($errors->all() as $message)
                        <li>{{ $message }}</li>
                    @endforeach
                </ul>
            </div>
        @endif

        {{ $slot }}
    </main>

    <footer class="border-t border-slate-200 bg-white">
        <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-slate-500 sm:px-6">
            <span>HRIS Rumatku • Modul Payroll Terintegrasi ROSY • Prototipe lokal</span>
            <span>PP 58/2023 (TER) · UU HPP Pasal 17 · PP 35/2021</span>
        </div>
    </footer>
</div>
@livewireScripts
</body>
</html>
