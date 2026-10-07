<?php

namespace App\Support;

/** Angka → kalimat terbilang Bahasa Indonesia, mis. "Delapan Juta Tujuh Ratus ... Rupiah". */
final class Terbilang
{
    private const DIGITS = ['', 'Satu', 'Dua', 'Tiga', 'Empat', 'Lima', 'Enam', 'Tujuh', 'Delapan', 'Sembilan'];

    private const SCALES = [
        1_000_000_000_000 => 'Triliun',
        1_000_000_000 => 'Miliar',
        1_000_000 => 'Juta',
        1_000 => 'Ribu',
    ];

    public static function rupiah(int|float|string $amount): string
    {
        return self::words(Money::round($amount)).' Rupiah';
    }

    public static function words(int $number): string
    {
        if ($number === 0) {
            return 'Nol';
        }
        if ($number < 0) {
            return 'Minus '.self::words(-$number);
        }

        $parts = [];
        foreach (self::SCALES as $scale => $label) {
            if ($number >= $scale) {
                $chunk = intdiv($number, $scale);
                $number %= $scale;
                // "Seribu", bukan "Satu Ribu" — hanya untuk ribuan.
                $parts[] = ($scale === 1_000 && $chunk === 1) ? 'Seribu' : self::belowThousand($chunk).' '.$label;
            }
        }
        if ($number > 0) {
            $parts[] = self::belowThousand($number);
        }

        return implode(' ', $parts);
    }

    private static function belowThousand(int $n): string
    {
        $parts = [];
        if ($n >= 100) {
            $hundreds = intdiv($n, 100);
            $parts[] = $hundreds === 1 ? 'Seratus' : self::DIGITS[$hundreds].' Ratus';
            $n %= 100;
        }
        if ($n >= 20) {
            $parts[] = self::DIGITS[intdiv($n, 10)].' Puluh';
            $n %= 10;
            if ($n > 0) {
                $parts[] = self::DIGITS[$n];
            }
        } elseif ($n >= 12) {
            $parts[] = self::DIGITS[$n - 10].' Belas';
        } elseif ($n === 11) {
            $parts[] = 'Sebelas';
        } elseif ($n === 10) {
            $parts[] = 'Sepuluh';
        } elseif ($n > 0) {
            $parts[] = self::DIGITS[$n];
        }

        return implode(' ', $parts);
    }
}
