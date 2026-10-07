<?php

namespace App\Casts;

use App\Support\Money;
use Illuminate\Contracts\Database\Eloquent\CastsAttributes;
use Illuminate\Database\Eloquent\Model;

/** Kolom DECIMAL(15,2) dibaca sebagai int rupiah dan ditulis kembali sebagai desimal. */
class Rupiah implements CastsAttributes
{
    public function get(Model $model, string $key, mixed $value, array $attributes): ?int
    {
        return $value === null ? null : Money::round($value);
    }

    public function set(Model $model, string $key, mixed $value, array $attributes): ?string
    {
        return $value === null ? null : number_format(Money::round($value), 2, '.', '');
    }
}
