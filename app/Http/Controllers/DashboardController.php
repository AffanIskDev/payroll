<?php

namespace App\Http\Controllers;

use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

class DashboardController extends Controller
{
    /** Arahkan ke halaman utama sesuai peran. */
    public function __invoke(Request $request): RedirectResponse
    {
        return redirect()->route($request->user()->homeRoute());
    }
}
