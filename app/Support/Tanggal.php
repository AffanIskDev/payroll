<?php

namespace App\Support;

use Carbon\CarbonInterface;
use Illuminate\Support\Carbon;

/** Format tanggal Indonesia yang dipakai di slip dan layar. */
final class Tanggal
{
    public const BULAN = [
        1 => 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
        'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
    ];

    public const BULAN_PENDEK = [
        1 => 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des',
    ];

    /** 2026-04-01 → "01 April 2026" */
    public static function panjang(CarbonInterface|string|null $date): string
    {
        if ($date === null) {
            return '-';
        }
        $d = $date instanceof CarbonInterface ? $date : Carbon::parse($date);

        return $d->format('d').' '.self::BULAN[(int) $d->format('n')].' '.$d->format('Y');
    }

    /** "Maret 2026" */
    public static function bulanTahun(CarbonInterface $date): string
    {
        return self::BULAN[(int) $date->format('n')].' '.$date->format('Y');
    }
}
