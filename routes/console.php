<?php

use Illuminate\Support\Facades\Schedule;

/*
| PRD langkah 1: trigger periode di tanggal akhir bulan. Butuh cron
| `* * * * * php8.3 artisan schedule:run` (atau `php8.3 artisan schedule:work`).
*/
Schedule::command('payroll:generate')
    ->lastDayOfMonth('20:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping();
