<?php

namespace App\Services\Payroll;

use App\Support\Money;
use InvalidArgumentException;

/**
 * PPh 21 bulanan metode TER (PP 58/2023) untuk masa pajak Januari–November.
 * PPh 21 = Bruto sebulan × tarif TER kategori PTKP pada lapisan bruto tersebut.
 */
class Pph21TerCalculatorService
{
    /** PTKP setahun (UU HPP). */
    public const PTKP = [
        'TK/0' => 54_000_000,
        'TK/1' => 58_500_000,
        'TK/2' => 63_000_000,
        'TK/3' => 67_500_000,
        'K/0' => 58_500_000,
        'K/1' => 63_000_000,
        'K/2' => 67_500_000,
        'K/3' => 72_000_000,
    ];

    public const CATEGORY = [
        'TK/0' => 'A', 'TK/1' => 'A', 'K/0' => 'A',
        'TK/2' => 'B', 'TK/3' => 'B', 'K/1' => 'B', 'K/2' => 'B',
        'K/3' => 'C',
    ];

    /**
     * Lampiran PP 58/2023: [batas atas bruto (inklusif), tarif dalam basis poin].
     * Batas bawah tiap lapisan eksklusif ("> x s.d. y"); null = tanpa batas atas.
     * Dicocokkan dengan seed config_ter ROSY (A 44, B 40, C 41 lapisan).
     */
    public const BRACKETS = [
        'A' => [
            [5_400_000, 0], [5_650_000, 25], [5_950_000, 50], [6_300_000, 75], [6_750_000, 100],
            [7_500_000, 125], [8_550_000, 150], [9_650_000, 175], [10_050_000, 200], [10_350_000, 225],
            [10_700_000, 250], [11_050_000, 300], [11_600_000, 350], [12_500_000, 400], [13_750_000, 500],
            [15_100_000, 600], [16_950_000, 700], [19_750_000, 800], [24_150_000, 900], [26_450_000, 1000],
            [28_000_000, 1100], [30_050_000, 1200], [32_400_000, 1300], [35_400_000, 1400], [39_100_000, 1500],
            [43_850_000, 1600], [47_800_000, 1700], [51_400_000, 1800], [56_300_000, 1900], [62_200_000, 2000],
            [68_600_000, 2100], [77_500_000, 2200], [89_000_000, 2300], [103_000_000, 2400], [125_000_000, 2500],
            [157_000_000, 2600], [206_000_000, 2700], [337_000_000, 2800], [454_000_000, 2900], [550_000_000, 3000],
            [695_000_000, 3100], [910_000_000, 3200], [1_400_000_000, 3300], [null, 3400],
        ],
        'B' => [
            [6_200_000, 0], [6_500_000, 25], [6_850_000, 50], [7_300_000, 75], [9_200_000, 100],
            [10_750_000, 150], [11_250_000, 200], [11_600_000, 250], [12_600_000, 300], [13_600_000, 400],
            [14_950_000, 500], [16_400_000, 600], [18_450_000, 700], [21_850_000, 800], [26_000_000, 900],
            [27_700_000, 1000], [29_350_000, 1100], [31_450_000, 1200], [33_950_000, 1300], [37_100_000, 1400],
            [41_100_000, 1500], [45_800_000, 1600], [49_500_000, 1700], [53_800_000, 1800], [58_500_000, 1900],
            [64_000_000, 2000], [71_000_000, 2100], [80_000_000, 2200], [93_000_000, 2300], [109_000_000, 2400],
            [129_000_000, 2500], [163_000_000, 2600], [211_000_000, 2700], [374_000_000, 2800], [459_000_000, 2900],
            [555_000_000, 3000], [704_000_000, 3100], [957_000_000, 3200], [1_405_000_000, 3300], [null, 3400],
        ],
        'C' => [
            [6_600_000, 0], [6_950_000, 25], [7_350_000, 50], [7_800_000, 75], [8_850_000, 100],
            [9_800_000, 125], [10_950_000, 150], [11_200_000, 175], [12_050_000, 200], [12_950_000, 300],
            [14_150_000, 400], [15_550_000, 500], [17_050_000, 600], [19_500_000, 700], [22_700_000, 800],
            [26_600_000, 900], [28_100_000, 1000], [30_100_000, 1100], [32_600_000, 1200], [35_400_000, 1300],
            [38_900_000, 1400], [43_000_000, 1500], [47_400_000, 1600], [51_200_000, 1700], [55_800_000, 1800],
            [60_400_000, 1900], [66_700_000, 2000], [74_500_000, 2100], [83_200_000, 2200], [95_600_000, 2300],
            [110_000_000, 2400], [134_000_000, 2500], [169_000_000, 2600], [221_000_000, 2700], [390_000_000, 2800],
            [463_000_000, 2900], [561_000_000, 3000], [709_000_000, 3100], [965_000_000, 3200], [1_419_000_000, 3300],
            [null, 3400],
        ],
    ];

    /** "k1", "K-1", "K/1" → "K/1". */
    public static function normalizeStatus(string $status): string
    {
        $clean = strtoupper(preg_replace('/[^A-Za-z0-9]/', '', $status) ?? '');
        if (! preg_match('/^(TK|K)([0-3])$/', $clean, $m)) {
            throw new InvalidArgumentException("Status PTKP tidak dikenal: {$status}");
        }

        return $m[1].'/'.$m[2];
    }

    public function category(string $ptkpStatus): string
    {
        return self::CATEGORY[self::normalizeStatus($ptkpStatus)];
    }

    public function ptkp(string $ptkpStatus): int
    {
        return self::PTKP[self::normalizeStatus($ptkpStatus)];
    }

    /** @return array{lower: int, upper: ?int, rate_bp: int} */
    public function bracket(string $category, int $gross): array
    {
        if (! isset(self::BRACKETS[$category])) {
            throw new InvalidArgumentException("Kategori TER tidak dikenal: {$category}");
        }

        $lower = 0;
        foreach (self::BRACKETS[$category] as [$upper, $bp]) {
            if ($upper === null || $gross <= $upper) {
                return ['lower' => $lower, 'upper' => $upper, 'rate_bp' => $bp];
            }
            $lower = $upper;
        }

        throw new \LogicException('Tabel TER tidak lengkap.');
    }

    /** Modul 1B: PPh 21 = round(bruto × tarif TER). */
    public function calculateMonthlyTer(float $taxableGross, string $ptkpStatus): float
    {
        return (float) $this->calculate(Money::round($taxableGross), $ptkpStatus)['amount'];
    }

    /**
     * @return array{ptkp_status: string, category: string, rate_bp: int, lower: int, upper: ?int, gross: int, amount: int}
     */
    public function calculate(int $gross, string $ptkpStatus): array
    {
        $status = self::normalizeStatus($ptkpStatus);
        $category = self::CATEGORY[$status];
        $bracket = $this->bracket($category, max(0, $gross));

        return [
            'ptkp_status' => $status,
            'category' => $category,
            'rate_bp' => $bracket['rate_bp'],
            'lower' => $bracket['lower'],
            'upper' => $bracket['upper'],
            'gross' => $gross,
            'amount' => $gross > 0 ? Money::pctBp($gross, $bracket['rate_bp']) : 0,
        ];
    }
}
