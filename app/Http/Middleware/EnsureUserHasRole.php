<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/** Pemakaian: ->middleware('role:MANAGER_HRD') atau 'role:MANAGER_HRD,STAFF_HRD'. */
class EnsureUserHasRole
{
    public function handle(Request $request, Closure $next, string ...$roles): Response
    {
        $user = $request->user();

        if (! $user || ! $user->hasRole(...$roles)) {
            abort(403, 'Halaman ini hanya untuk peran: '.implode(', ', $roles).'.');
        }

        return $next($request);
    }
}
