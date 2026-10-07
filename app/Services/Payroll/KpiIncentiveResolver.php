<?php

namespace App\Services\Payroll;

use App\Support\Money;

/**
 * Konversi skor KPI ROSY ke nominal insentif (Modul 2A langkah d).
 * Nominal dari ROSY dipakai apa adanya; kalau kosong, pakai tabel
 * KPI_INCENTIVE_TIERS (skor >= min → amount).
 */
class KpiIncentiveResolver
{
    public function __construct(private readonly PayrollSettings $settings) {}

    /**
     * @param  array{score: float, incentive_amount: ?int}|null  $kpi
     */
    public function resolve(?array $kpi): int
    {
        if ($kpi === null) {
            return 0;
        }
        if ($kpi['incentive_amount'] !== null) {
            return Money::round($kpi['incentive_amount']);
        }

        $tiers = collect($this->settings->json('KPI_INCENTIVE_TIERS'))
            ->filter(fn ($tier) => isset($tier['min'], $tier['amount']))
            ->sortByDesc('min');

        foreach ($tiers as $tier) {
            if ($kpi['score'] >= (float) $tier['min']) {
                return Money::round($tier['amount']);
            }
        }

        return 0;
    }
}
