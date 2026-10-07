<?php

namespace App\Services\Payroll;

use App\Models\Payslip;
use App\Support\Tanggal;
use Barryvdh\DomPDF\Facade\Pdf;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

/**
 * Render slip gaji (Blade → PDF) dan enkripsi dengan password tanggal lahir
 * karyawan format DDMMYY (Modul 3A).
 */
class PayslipPdfService
{
    public function __construct(
        private readonly PayslipPresenter $presenter,
        private readonly PdfEncryptor $encryptor,
    ) {}

    /** Render, enkripsi, simpan; kembalikan path relatif di disk payroll. */
    public function generate(Payslip $payslip): string
    {
        $payslip->loadMissing(['period', 'employee']);
        $period = $payslip->period;

        $password = Carbon::parse($payslip->employee->birth_date)->format('dmy');
        // Metadata PDF tidak terenkripsi: hanya isi yang tidak menyebut identitas karyawan.
        $encrypted = $this->encryptor->encrypt($this->render($payslip), $password, [
            'title' => 'Slip Gaji Elektronik '.$period->period_name,
            'author' => 'HRIS ROSY',
            'subject' => 'Dokumen Rahasia',
        ]);

        $path = sprintf('payslips/%04d/%02d/%d_%s.pdf', $period->year(), $period->month(), $payslip->id, Str::lower(Str::random(20)));
        $disk = Storage::disk(config('payroll.disk'));
        $disk->put($path, $encrypted);

        if ($payslip->pdf_path && $payslip->pdf_path !== $path) {
            $disk->delete($payslip->pdf_path);
        }

        $payslip->forceFill([
            'pdf_path' => $path,
            'pdf_password_hash' => Hash::make($password),
            'pdf_generated_at' => now(),
            'pdf_error' => null,
        ])->save();

        return $path;
    }

    /** PDF tanpa enkripsi (untuk pratinjau Manager HRD). */
    public function render(Payslip $payslip, bool $previewWatermark = false): string
    {
        $html = view('pdf.payslip', [
            'slip' => $this->presenter->present($payslip),
            'watermark' => $previewWatermark ? 'PRATINJAU' : null,
            'generatedAt' => Tanggal::panjang(now()).' '.now()->format('H:i'),
        ])->render();

        return Pdf::loadHTML($html)
            ->setPaper('a4', 'portrait')
            ->setOption(['defaultFont' => 'Roboto', 'isRemoteEnabled' => false, 'dpi' => 96])
            ->output();
    }

    public function downloadName(Payslip $payslip): string
    {
        $payslip->loadMissing('period');

        return sprintf('Slip_Gaji_%s_%s.pdf', str_replace('-', '_', $payslip->period->period_code), $payslip->employee_nik);
    }
}
