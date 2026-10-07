<?php

namespace Database\Seeders;

use App\Models\PayrollConfig;
use Illuminate\Database\Seeder;

/** Parameter payroll bawaan (tidak menimpa nilai yang sudah diubah). */
class PayrollConfigSeeder extends Seeder
{
    public function run(): void
    {
        foreach (PayrollConfig::DEFINITIONS as $key => $definition) {
            PayrollConfig::firstOrCreate(
                ['config_key' => $key],
                ['config_value' => $definition['default'], 'description' => $definition['description']],
            );
        }
    }
}
