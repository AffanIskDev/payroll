<?php

namespace App\Services\Payroll;

use setasign\Fpdi\PdfParser\StreamReader;
use setasign\Fpdi\Tcpdf\Fpdi;

/**
 * Membungkus ulang PDF hasil dompdf dengan enkripsi AES-128 (Standard
 * Security Handler V4/R4). Enkripsi bawaan dompdf hanya RC4 40-bit yang
 * kuncinya bisa dibobol tanpa password.
 *
 * PERHATIAN: TCPDF menulis metadata XMP (judul, penulis, subjek) TANPA
 * enkripsi. Jangan pernah mengisi $meta dengan nama, NIK, atau nominal gaji.
 */
class PdfEncryptor
{
    /** Izin yang diblokir; mencetak dan menyalin teks tetap boleh. */
    private const BLOCKED_PERMISSIONS = ['modify', 'annot-forms', 'fill-forms', 'assemble'];

    private const MODE_AES_128 = 2;

    /**
     * @param  array{title?: string, author?: string, subject?: string}  $meta
     */
    public function encrypt(string $pdfBytes, string $userPassword, array $meta = []): string
    {
        $pdf = new Fpdi('P', 'pt', 'A4', true, 'UTF-8', false);
        $pdf->setPrintHeader(false);
        $pdf->setPrintFooter(false);
        $pdf->SetMargins(0, 0, 0);
        $pdf->SetAutoPageBreak(false, 0);

        // Harus dipanggil sebelum halaman pertama ditambahkan.
        $pdf->SetProtection(self::BLOCKED_PERMISSIONS, $userPassword, bin2hex(random_bytes(16)), self::MODE_AES_128);

        $pdf->SetCreator('ROSY Payroll');
        $pdf->SetAuthor($meta['author'] ?? 'ROSY Payroll');
        $pdf->SetTitle($meta['title'] ?? 'Dokumen Rahasia');
        $pdf->SetSubject($meta['subject'] ?? '');

        $pageCount = $pdf->setSourceFile(StreamReader::createByString($pdfBytes));
        for ($i = 1; $i <= $pageCount; $i++) {
            $template = $pdf->importPage($i);
            $size = $pdf->getTemplateSize($template);
            $pdf->AddPage($size['orientation'], [$size['width'], $size['height']]);
            $pdf->useTemplate($template);
        }

        return $pdf->Output('', 'S');
    }
}
