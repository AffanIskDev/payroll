<?php

return [

    /*
    | Disk penyimpanan PDF slip & dokumen pajak. Bawaan "payroll" menulis ke
    | storage/app (path: payslips/{tahun}/{bulan}/{id}_{hash}.pdf). Ganti ke
    | disk S3 di produksi.
    */
    'disk' => env('PAYROLL_DISK', 'payroll'),

    /*
    | Notifikasi ke aplikasi Rumatku saat slip terbit. Kalau URL kosong,
    | notifikasi hanya tersimpan di database (menu Slip Gaji tetap membaca API).
    */
    'rumatku' => [
        'webhook_url' => env('RUMATKU_WEBHOOK_URL'),
        'webhook_secret' => env('RUMATKU_WEBHOOK_SECRET'),
        'timeout' => (int) env('RUMATKU_WEBHOOK_TIMEOUT', 5),
    ],

    /* Tampilkan daftar akun demo di halaman login (hanya APP_ENV=local). */
    'show_demo_accounts' => (bool) env('PAYROLL_SHOW_DEMO_ACCOUNTS', true),

];
