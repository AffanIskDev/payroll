<?php

namespace Tests\Unit\Payroll;

use App\Support\Money;
use App\Support\Terbilang;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class MoneyAndTerbilangTest extends TestCase
{
    public function test_persentase_basis_poin_tanpa_galat_float(): void
    {
        $this->assertSame(14_400, Money::pctBp(6_000_000, Money::rateToBp(0.0024)));
        $this->assertSame(148_716, Money::pctBp(9_914_400, 150));
        $this->assertSame(1, Money::pctBp(5, 1000));    // 10% × 5 = 0,5 → dibulatkan ke atas
        $this->assertSame(0, Money::pctBp(4, 1000));    // 10% × 4 = 0,4 → dibulatkan ke bawah
        $this->assertSame(24, Money::rateToBp('0.24%'));
    }

    public function test_pecahan_penalti_dibulatkan_setengah_ke_atas(): void
    {
        $this->assertSame(80_000, Money::fraction(1_000_000, 2, 25));
        $this->assertSame(33_333, Money::fraction(1_000_000, 1, 30));
        $this->assertSame(66_667, Money::fraction(1_000_000, 2, 30));
    }

    public function test_format_rupiah(): void
    {
        $this->assertSame('Rp 8.731.284', Money::rupiah(8_731_284));
        $this->assertSame('-Rp 125.000', Money::rupiah(-125_000));
        $this->assertSame('1.50%', Money::bpToPercent(150, true));
        $this->assertSame('0.3%', Money::bpToPercent(30));
        $this->assertSame('2%', Money::bpToPercent(200));
    }

    #[DataProvider('terbilangProvider')]
    public function test_terbilang(int $angka, string $kalimat): void
    {
        $this->assertSame($kalimat, Terbilang::rupiah($angka));
    }

    public static function terbilangProvider(): array
    {
        return [
            'contoh slip' => [8_731_284, 'Delapan Juta Tujuh Ratus Tiga Puluh Satu Ribu Dua Ratus Delapan Puluh Empat Rupiah'],
            'seribu' => [1_000, 'Seribu Rupiah'],
            'seratus ribu' => [100_000, 'Seratus Ribu Rupiah'],
            'sebelas' => [11, 'Sebelas Rupiah'],
            'belasan ribu' => [15_000, 'Lima Belas Ribu Rupiah'],
            'satu juta' => [1_000_000, 'Satu Juta Rupiah'],
            'miliar' => [2_000_001_000, 'Dua Miliar Seribu Rupiah'],
            'nol' => [0, 'Nol Rupiah'],
            'minus' => [-1_500, 'Minus Seribu Lima Ratus Rupiah'],
        ];
    }
}
