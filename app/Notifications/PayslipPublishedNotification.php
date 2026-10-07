<?php

namespace App\Notifications;

use App\Models\Payslip;
use App\Notifications\Channels\RumatkuWebhookChannel;
use App\Support\Money;
use Illuminate\Notifications\Notification;

/** Notifikasi "slip gaji terbit" untuk karyawan (PRD langkah 6). */
class PayslipPublishedNotification extends Notification
{
    public function __construct(public Payslip $payslip) {}

    /** @return list<string> */
    public function via(object $notifiable): array
    {
        return ['database', RumatkuWebhookChannel::class];
    }

    /** @return array<string, mixed> */
    public function toArray(object $notifiable): array
    {
        $this->payslip->loadMissing('period');

        return [
            'type' => 'payslip_published',
            'payslip_id' => $this->payslip->id,
            'period_code' => $this->payslip->period->period_code,
            'period_name' => $this->payslip->period->period_name,
            'take_home_pay' => $this->payslip->take_home_pay,
            'title' => 'Slip gaji '.$this->payslip->period->period_name.' sudah terbit',
            'body' => 'Take home pay '.Money::rupiah($this->payslip->take_home_pay)
                .'. Buka menu Slip Gaji; password PDF = tanggal lahir (DDMMYY).',
        ];
    }

    /** @return array<string, mixed> */
    public function toRumatku(object $notifiable): array
    {
        return $this->toArray($notifiable) + [
            'employee_nik' => $this->payslip->employee_nik,
            'download_path' => '/api/v1/employee/payslips/'.$this->payslip->id.'/download',
        ];
    }
}
