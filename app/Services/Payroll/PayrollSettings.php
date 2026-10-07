<?php

namespace App\Services\Payroll;

use App\Models\PayrollConfig;
use App\Support\Money;

/**
 * Akses parameter payroll (tabel payroll_configs) dengan nilai bawaan dari
 * PayrollConfig::DEFINITIONS. Didaftarkan sebagai scoped binding sehingga
 * dibaca ulang di setiap request / job.
 */
class PayrollSettings
{
    /** @var array<string, string>|null */
    private ?array $values = null;

    /** @return array<string, string> */
    public function all(): array
    {
        if ($this->values === null) {
            $defaults = array_map(fn (array $def) => (string) $def['default'], PayrollConfig::DEFINITIONS);
            $stored = PayrollConfig::query()->pluck('config_value', 'config_key')->all();
            $this->values = array_merge($defaults, $stored);
        }

        return $this->values;
    }

    public function get(string $key): ?string
    {
        return $this->all()[$key] ?? null;
    }

    public function money(string $key): int
    {
        return Money::round($this->get($key));
    }

    public function int(string $key): int
    {
        return (int) $this->get($key);
    }

    public function json(string $key): array
    {
        $decoded = json_decode((string) $this->get($key), true);

        return is_array($decoded) ? $decoded : [];
    }

    public function flush(): void
    {
        $this->values = null;
    }
}
