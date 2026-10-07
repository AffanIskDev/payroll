<?php

namespace App\Http\Controllers\Api\Employee;

use App\Http\Controllers\Controller;
use App\Services\Payroll\TaxReport1721A1Service;
use DomainException;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/** Modul 5B: GET /api/v1/employee/tax-documents/{year} — 1721-A1 terenkripsi DDMMYY. */
class TaxDocumentApiController extends Controller
{
    public function show(Request $request, int $year, TaxReport1721A1Service $service): Response
    {
        $employee = $request->user()->employee;
        abort_unless($employee, 403, 'Akun tidak terhubung ke data karyawan.');

        try {
            $pdf = $service->encryptedPdf($employee, $year);
        } catch (DomainException $e) {
            abort(404, $e->getMessage());
        }

        return response($pdf, 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.$service->filename($employee, $year).'"',
            'Cache-Control' => 'no-store, private',
        ]);
    }
}
