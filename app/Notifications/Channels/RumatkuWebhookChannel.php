<?php

namespace App\Notifications\Channels;

use Illuminate\Notifications\Notification;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Kirim notifikasi ke backend Rumatku (yang meneruskan push ke aplikasi).
 * Payload ditandatangani HMAC-SHA256 di header X-Rosy-Signature.
 * Kalau RUMATKU_WEBHOOK_URL kosong, kanal ini diam (notifikasi tetap tersimpan
 * di tabel notifications lewat kanal database).
 */
class RumatkuWebhookChannel
{
    public function send(object $notifiable, Notification $notification): void
    {
        $url = config('payroll.rumatku.webhook_url');
        if (blank($url) || ! method_exists($notification, 'toRumatku')) {
            return;
        }

        $payload = $notification->toRumatku($notifiable);
        $body = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $signature = hash_hmac('sha256', (string) $body, (string) config('payroll.rumatku.webhook_secret'));

        try {
            Http::timeout(config('payroll.rumatku.timeout'))
                ->withHeaders(['X-Rosy-Signature' => $signature])
                ->withBody((string) $body, 'application/json')
                ->post($url)
                ->throw();
        } catch (Throwable $e) {
            // Gagal kirim tidak boleh membatalkan publikasi slip; slip tetap bisa diambil lewat API.
            // Jangan log payload: berisi nominal gaji.
            Log::warning('Notifikasi Rumatku gagal dikirim', [
                'error' => $e->getMessage(),
                'payslip_id' => $payload['payslip_id'] ?? null,
            ]);
        }
    }
}
