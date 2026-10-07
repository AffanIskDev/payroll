<?php

namespace App\Support;

/**
 * Aritmetika rupiah dengan bilangan bulat supaya tidak ada galat float.
 *
 * Semua tarif payroll (BPJS, JKK, TER) adalah kelipatan 0,01%, jadi bisa
 * dinyatakan dalam basis poin (1 bp = 0,01%) tanpa kehilangan presisi.
 */
final class Money
{
    /** Bulatkan ke rupiah terdekat (setengah ke atas, simetris untuk negatif). */
    public static function round(int|float|string|null $value): int
    {
        if ($value === null || $value === '') {
            return 0;
        }

        return (int) round((float) $value, 0, PHP_ROUND_HALF_UP);
    }

    /** Ubah tarif desimal (0.0024) atau persen string ("0.24%") ke basis poin (24). */
    public static function rateToBp(int|float|string $rate): int
    {
        if (is_string($rate) && str_ends_with(trim($rate), '%')) {
            return (int) round((float) rtrim(trim($rate), '%') * 100);
        }

        return (int) round((float) $rate * 10000);
    }

    /** $amount × $bp / 10.000, dibulatkan setengah ke atas. */
    public static function pctBp(int $amount, int $bp): int
    {
        if ($amount < 0) {
            return -self::pctBp(-$amount, $bp);
        }

        return intdiv(2 * $amount * $bp + 10000, 20000);
    }

    /** $amount × $numerator / $denominator, dibulatkan setengah ke atas. */
    public static function fraction(int $amount, int $numerator, int $denominator): int
    {
        if ($denominator <= 0) {
            throw new \InvalidArgumentException('Penyebut harus lebih dari nol.');
        }
        if ($amount * $numerator < 0) {
            return -self::fraction(abs($amount), abs($numerator), $denominator);
        }

        return intdiv(2 * $amount * $numerator + $denominator, 2 * $denominator);
    }

    /** 6000000 → "6.000.000" */
    public static function format(int|float|string|null $value): string
    {
        $int = self::round($value);
        $formatted = number_format(abs($int), 0, ',', '.');

        return $int < 0 ? '-'.$formatted : $formatted;
    }

    /** 6000000 → "Rp 6.000.000" */
    public static function rupiah(int|float|string|null $value): string
    {
        $int = self::round($value);

        return ($int < 0 ? '-Rp ' : 'Rp ').number_format(abs($int), 0, ',', '.');
    }

    /** Basis poin → teks persen ala contoh slip: 24 → "0.24%", 150 → "1.50%" bila $fixed. */
    public static function bpToPercent(int $bp, bool $fixed = false): string
    {
        $value = $bp / 100;
        if ($fixed) {
            return number_format($value, 2, '.', '').'%';
        }

        return rtrim(rtrim(number_format($value, 2, '.', ''), '0'), '.').'%';
    }
}
