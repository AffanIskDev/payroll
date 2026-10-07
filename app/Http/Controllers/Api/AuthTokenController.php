<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\ValidationException;

/**
 * Token Sanctum untuk uji integrasi Rumatku. Di produksi, token sebaiknya
 * diterbitkan lewat SSO/akun Rumatku yang sudah ada, bukan email+password ROSY.
 */
class AuthTokenController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required', 'string'],
            'device_name' => ['nullable', 'string', 'max:100'],
        ]);

        $user = User::where('email', $data['email'])->first();
        if (! $user || ! Hash::check($data['password'], $user->password)) {
            throw ValidationException::withMessages(['email' => 'Email atau password salah.']);
        }
        if (! $user->employee_id) {
            throw ValidationException::withMessages(['email' => 'Akun tidak terhubung ke data karyawan.']);
        }

        $token = $user->createToken($data['device_name'] ?? 'rumatku-app', ['ess:payslip'])->plainTextToken;

        return response()->json([
            'status' => 'success',
            'data' => [
                'token_type' => 'Bearer',
                'access_token' => $token,
                'employee' => ['nik' => $user->employee->nik, 'name' => $user->employee->full_name],
            ],
        ], 201);
    }

    public function destroy(Request $request): JsonResponse
    {
        $request->user()->currentAccessToken()?->delete();

        return response()->json(['status' => 'success', 'message' => 'Token dicabut.']);
    }
}
