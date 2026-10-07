<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        $this->call(PayrollConfigSeeder::class);

        if (! app()->isProduction()) {
            $this->call(DemoPayrollSeeder::class);
        }
    }
}
