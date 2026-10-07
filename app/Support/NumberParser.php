<?php

namespace App\Support;

/**
 * Angka dari spreadsheet: 1234567 | 1234567.5 | "1.234.567" | "1.234.567,50" |
 * "1,234,567.50" | "Rp 1.234.567". Mengembalikan null kalau bukan angka.
 */
final class NumberParser
{
    public static function parse(mixed $value): ?float
    {
        if (is_int($value) || is_float($value)) {
            return (float) $value;
        }
        if (! is_string($value)) {
            return null;
        }

        $v = trim(str_ireplace(['rp', ' ', "\u{00A0}"], '', $value));
        if ($v === '') {
            return null;
        }

        // Format Indonesia: titik ribuan, koma desimal.
        if (preg_match('/^-?\d{1,3}(\.\d{3})+(,\d+)?$/', $v)) {
            return (float) str_replace(['.', ','], ['', '.'], $v);
        }
        // Format Inggris: koma ribuan, titik desimal ("1,234" dianggap seribu dua ratus tiga puluh empat).
        if (preg_match('/^-?\d{1,3}(,\d{3})+(\.\d+)?$/', $v)) {
            return (float) str_replace(',', '', $v);
        }
        // Koma desimal tanpa pemisah ribuan: "1234,5" / "1234,50".
        if (preg_match('/^-?\d+,\d{1,2}$/', $v)) {
            return (float) str_replace(',', '.', $v);
        }
        if (is_numeric($v)) {
            return (float) $v;
        }

        return null;
    }
}
