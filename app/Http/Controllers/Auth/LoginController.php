<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Validation\ValidationException;
use Illuminate\View\View;

class LoginController extends Controller
{
    public function show(): View
    {
        // Hanya di lingkungan lokal: satu akun per peran + contoh karyawan dari slip sampel.
        $demoAccounts = app()->isLocal() && config('payroll.show_demo_accounts')
            ? User::query()->with('employee:id,position')
                ->where('role', '<>', User::ROLE_KARYAWAN)
                ->orderByRaw("FIELD(role, 'MANAGER_HRD', 'STAFF_HRD', 'ATASAN_DIVISI')")
                ->get()
                ->merge(User::query()->with('employee:id,position')->where('role', User::ROLE_KARYAWAN)
                    ->orderByRaw("name = 'Budi Santoso' DESC")->orderBy('name')->limit(2)->get())
            : collect();

        return view('auth.login', compact('demoAccounts'));
    }

    public function login(Request $request): RedirectResponse
    {
        $credentials = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required', 'string'],
        ]);

        if (! Auth::attempt($credentials, $request->boolean('remember'))) {
            throw ValidationException::withMessages(['email' => 'Email atau password salah.']);
        }

        $request->session()->regenerate();

        return redirect()->intended(route($request->user()->homeRoute()));
    }

    public function logout(Request $request): RedirectResponse
    {
        Auth::guard('web')->logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }
}
