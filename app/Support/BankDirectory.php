<?php

namespace App\Support;

/** Nama lengkap bank untuk kode singkat yang tersimpan di profil gaji. */
final class BankDirectory
{
    public const BANKS = [
        'BSI' => 'Bank Syariah Indonesia (BSI)',
        'BCA' => 'Bank Central Asia (BCA)',
        'MANDIRI' => 'Bank Mandiri',
        'BRI' => 'Bank Rakyat Indonesia (BRI)',
        'BNI' => 'Bank Negara Indonesia (BNI)',
        'BTN' => 'Bank Tabungan Negara (BTN)',
        'CIMB' => 'CIMB Niaga',
        'PERMATA' => 'Bank Permata',
        'DANAMON' => 'Bank Danamon',
        'BJB' => 'Bank BJB',
    ];

    public static function label(?string $code): string
    {
        $key = strtoupper(trim((string) $code));

        return self::BANKS[$key] ?? (string) $code;
    }

    public static function isBsi(?string $code): bool
    {
        return strtoupper(trim((string) $code)) === 'BSI';
    }
}
