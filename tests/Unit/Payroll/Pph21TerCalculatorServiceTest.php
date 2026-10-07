<?php

namespace Tests\Unit\Payroll;

use App\Services\Payroll\Pph21TerCalculatorService;
use InvalidArgumentException;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class Pph21TerCalculatorServiceTest extends TestCase
{
    private Pph21TerCalculatorService $ter;

    protected function setUp(): void
    {
        parent::setUp();
        $this->ter = new Pph21TerCalculatorService;
    }

    public function test_contoh_slip_k1_ter_b_satu_setengah_persen(): void
    {
        $this->assertSame('B', $this->ter->category('K/1'));
        $this->assertSame(148_716.0, $this->ter->calculateMonthlyTer(9_914_400, 'K/1'));
    }

    public function test_pemetaan_kategori_ptkp(): void
    {
        foreach (['TK/0', 'TK/1', 'K/0'] as $s) {
            $this->assertSame('A', $this->ter->category($s));
        }
        foreach (['TK/2', 'TK/3', 'K/1', 'K/2'] as $s) {
            $this->assertSame('B', $this->ter->category($s));
        }
        $this->assertSame('C', $this->ter->category('K/3'));
    }

    #[DataProvider('bracketProvider')]
    public function test_batas_lapisan_inklusif_di_batas_atas(string $status, int $gross, int $expectedBp): void
    {
        $this->assertSame($expectedBp, $this->ter->calculate($gross, $status)['rate_bp']);
    }

    public static function bracketProvider(): array
    {
        return [
            'A tepat 5,4 jt → 0%' => ['TK/0', 5_400_000, 0],
            'A 5,4 jt + 1 → 0,25%' => ['TK/0', 5_400_001, 25],
            'A 10 jt → 2%' => ['TK/0', 10_000_000, 200],
            'A di atas 1,4 M → 34%' => ['TK/0', 1_500_000_000, 3400],
            'B tepat 6,2 jt → 0%' => ['K/1', 6_200_000, 0],
            'B 9,2 jt → 1%' => ['K/1', 9_200_000, 100],
            'B 9,2 jt + 1 → 1,5%' => ['K/1', 9_200_001, 150],
            'C 6,6 jt → 0%' => ['K/3', 6_600_000, 0],
            'C 12,95 jt → 3%' => ['K/3', 12_950_000, 300],
            'C di atas 1,419 M → 34%' => ['K/3', 1_419_000_001, 3400],
        ];
    }

    public function test_jumlah_lapisan_sesuai_pp_58_2023(): void
    {
        $this->assertCount(44, Pph21TerCalculatorService::BRACKETS['A']);
        $this->assertCount(40, Pph21TerCalculatorService::BRACKETS['B']);
        $this->assertCount(41, Pph21TerCalculatorService::BRACKETS['C']);
    }

    public function test_normalisasi_dan_validasi_status_ptkp(): void
    {
        $this->assertSame('K/1', Pph21TerCalculatorService::normalizeStatus('k1'));
        $this->assertSame('TK/0', Pph21TerCalculatorService::normalizeStatus('TK-0'));

        $this->expectException(InvalidArgumentException::class);
        Pph21TerCalculatorService::normalizeStatus('K/4');
    }
}
