@php
    use App\Support\Money;
    $fontDir = resource_path('fonts');
    $houseIcon = 'data:image/svg+xml;base64,'.base64_encode('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#111827" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>');
    $rows = max(count($slip['earnings']), count($slip['deductions']));
@endphp
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Slip Gaji {{ $slip['employee_name'] }}</title>
<style>
    @font-face { font-family: 'Roboto'; font-style: normal; font-weight: 400; src: url('{{ $fontDir }}/Roboto-Regular.ttf') format('truetype'); }
    @font-face { font-family: 'Roboto'; font-style: normal; font-weight: 700; src: url('{{ $fontDir }}/Roboto-Bold.ttf') format('truetype'); }
    @font-face { font-family: 'Roboto'; font-style: italic; font-weight: 400; src: url('{{ $fontDir }}/Roboto-Italic.ttf') format('truetype'); }

    @page { margin: 28pt 36pt 40pt 36pt; }
    * { box-sizing: border-box; }
    body { font-family: 'Roboto', sans-serif; font-size: 8.4pt; line-height: 1.18; color: #1f2937; margin: 0; }
    table { border-collapse: collapse; width: 100%; }
    td { vertical-align: top; }
    .b { font-weight: 700; }
    .right { text-align: right; }
    .center { text-align: center; }
    .muted { color: #64748b; }

    .brand { font-size: 17pt; font-weight: 700; color: #111827; }
    .brand img { vertical-align: -3pt; margin-right: 4pt; }
    .tagline { color: #64748b; font-size: 8.6pt; margin-top: 3pt; }
    .doc-title { font-size: 13pt; font-weight: 700; color: #1e40af; }
    .doc-period { font-size: 8.6pt; font-weight: 700; color: #1f2937; margin-top: 3pt; }
    .badge { display: inline-block; margin-top: 5pt; padding: 2pt 7pt; border: 0.8pt solid #fecaca; background: #fef2f2; color: #b91c1c; font-size: 7pt; font-weight: 700; border-radius: 3pt; letter-spacing: 0.4pt; }
    .rule { border-top: 2.6pt solid #111827; margin: 9pt 0 10pt 0; }

    .box { border: 0.8pt solid #e2e8f0; background: #f8fafc; border-radius: 5pt; padding: 5pt 10pt; }
    .meta td { padding: 2.2pt 0; border-bottom: 0.6pt dotted #e2e8f0; font-size: 8.2pt; }
    .meta tr:last-child td { border-bottom: none; }
    .meta .k { color: #64748b; }
    .meta .v { font-weight: 700; text-align: right; color: #111827; }

    .stats { margin-top: 8pt; border: 0.8pt solid #bfdbfe; background: #eff6ff; border-radius: 5pt; }
    .stats td { text-align: center; padding: 5pt 4pt; width: 25%; }
    .stats .label { font-size: 6.8pt; font-weight: 700; color: #1d4ed8; letter-spacing: 0.3pt; }
    .stats .value { font-size: 11pt; font-weight: 700; color: #1e3a8a; margin-top: 2pt; }

    .comp { margin-top: 8pt; }
    .comp td { padding: 3.2pt 9pt; }
    .comp .gap { width: 12pt; padding: 0; border: none; background: #ffffff; }
    .comp .head-e { background: #ecfdf5; color: #047857; font-weight: 700; font-size: 8pt; border-top: 0.8pt solid #a7f3d0; border-bottom: 0.8pt solid #a7f3d0; }
    .comp .head-d { background: #fef2f2; color: #b91c1c; font-weight: 700; font-size: 8pt; border-top: 0.8pt solid #fecaca; border-bottom: 0.8pt solid #fecaca; }
    .comp .l-e { border-left: 0.8pt solid #d1fae5; }
    .comp .r-e { border-right: 0.8pt solid #d1fae5; }
    .comp .l-d { border-left: 0.8pt solid #fee2e2; }
    .comp .r-d { border-right: 0.8pt solid #fee2e2; }
    .comp .item { height: 21pt; }
    .comp .name { font-size: 8.5pt; color: #111827; }
    .comp .cap { font-size: 6.7pt; color: #6b7280; margin-top: 0.5pt; }
    .comp .amt { text-align: right; font-weight: 700; font-size: 8.5pt; color: #111827; white-space: nowrap; }
    .comp .total td.t { background: #f8fafc; font-weight: 700; font-size: 8.8pt; padding-top: 5pt; padding-bottom: 5pt; }
    .comp .total .t-e { border-top: 0.8pt solid #d1fae5; border-bottom: 0.8pt solid #d1fae5; }
    .comp .total .t-d { border-top: 0.8pt solid #fee2e2; border-bottom: 0.8pt solid #fee2e2; }
    .green { color: #047857; }
    .red { color: #b91c1c; }

    .thp { margin-top: 9pt; background: #0f172a; border-radius: 5pt; }
    .thp td { padding: 8pt 12pt; vertical-align: middle; }
    .thp .title { color: #e2e8f0; font-weight: 700; font-size: 9.6pt; letter-spacing: 0.4pt; }
    .thp .words { color: #cbd5e1; font-style: italic; font-size: 8.2pt; margin-top: 3pt; }
    .thp .amount { color: #38bdf8; font-weight: 700; font-size: 18pt; text-align: right; white-space: nowrap; }
    .thp .calc { color: #94a3b8; font-size: 7pt; text-align: right; margin-top: 2pt; }

    .info { margin-top: 8pt; }
    .info td.cell { border: 0.8pt solid #e2e8f0; border-radius: 5pt; padding: 6pt 10pt; }
    .info .h { font-size: 7.4pt; font-weight: 700; color: #374151; letter-spacing: 0.2pt; }
    .info .bank { font-size: 9pt; font-weight: 700; color: #111827; margin-top: 3pt; }
    .info .txt { font-size: 7.8pt; color: #4b5563; margin-top: 2pt; line-height: 1.35; }

    .sign { margin-top: 8pt; }
    .sign td.cell { border: 0.8pt dashed #cbd5e1; border-radius: 5pt; padding: 6pt 10pt 7pt 10pt; text-align: center; background: #fcfdfe; }
    .sign .caption { color: #64748b; font-size: 7.8pt; }
    .sign .line { width: 150pt; margin: 24pt auto 3pt auto; border-top: 0.8pt solid #64748b; }
    .sign .name { font-weight: 700; font-size: 8.6pt; color: #111827; }
    .sign .role { color: #64748b; font-size: 7.4pt; margin-top: 1pt; }

    .footer { position: fixed; bottom: -24pt; left: 0; right: 0; border-top: 0.8pt dashed #cbd5e1; padding-top: 5pt; font-size: 7.2pt; color: #64748b; }
    .watermark { position: fixed; top: 300pt; left: 40pt; right: 40pt; text-align: center; font-size: 66pt; font-weight: 700; color: #94a3b8; opacity: 0.12; transform: rotate(-30deg); }
</style>
</head>
<body>
@if ($watermark)
    <div class="watermark">{{ $watermark }}</div>
@endif

<div class="footer">
    <table><tr>
        <td>HRIS Rumatku • Modul Payroll Terintegrasi ROSY • Dokumen Rahasia</td>
        <td class="right">Dibuat {{ $generatedAt }} &nbsp;•&nbsp; Halaman 1 dari 1</td>
    </tr></table>
</div>

<table>
    <tr>
        <td style="width:60%">
            <div class="brand"><img src="{{ $houseIcon }}" style="width:18pt;height:18pt" alt="">ROSY | RUMATKU HRIS</div>
            <div class="tagline">{{ $slip['company_name'] }} • Sistem Penggajian &amp; Remunerasi Karyawan</div>
        </td>
        <td class="right" style="width:40%">
            <div class="doc-title">SLIP GAJI ELEKTRONIK</div>
            <div class="doc-period">{{ $slip['period_label'] }}</div>
            <span class="badge">RAHASIA &amp; PRIBADI</span>
        </td>
    </tr>
</table>
<div class="rule"></div>

<div class="box">
    <table>
        <tr>
            <td style="width:48%">
                <table class="meta">
                    @foreach ($slip['meta_left'] as [$k, $v])
                        <tr><td class="k">{{ $k }}</td><td class="v">{{ $v }}</td></tr>
                    @endforeach
                </table>
            </td>
            <td style="width:4%"></td>
            <td style="width:48%">
                <table class="meta">
                    @foreach ($slip['meta_right'] as [$k, $v])
                        <tr><td class="k">{{ $k }}</td><td class="v">{{ $v }}</td></tr>
                    @endforeach
                </table>
            </td>
        </tr>
    </table>
</div>

<table class="stats">
    <tr>
        @foreach ($slip['stats'] as [$label, $value])
            <td><div class="label">{{ $label }}</div><div class="value">{{ $value }}</div></td>
        @endforeach
    </tr>
</table>

<table class="comp">
    <tr>
        <td class="head-e l-e">KOMPONEN PENERIMAAN (A)</td>
        <td class="head-e r-e right">JUMLAH (RP)</td>
        <td class="gap"></td>
        <td class="head-d l-d">KOMPONEN POTONGAN (B)</td>
        <td class="head-d r-d right">JUMLAH (RP)</td>
    </tr>
    @for ($i = 0; $i < $rows; $i++)
        @php $e = $slip['earnings'][$i] ?? null; $d = $slip['deductions'][$i] ?? null; @endphp
        <tr class="item">
            <td class="l-e">
                @if ($e)<div class="name">{{ $e['label'] }}</div><div class="cap">{{ $e['caption'] }}</div>@endif
            </td>
            <td class="r-e amt">{{ $e ? Money::format($e['amount']) : '' }}</td>
            <td class="gap"></td>
            <td class="l-d">
                @if ($d)<div class="name">{{ $d['label'] }}</div><div class="cap">{{ $d['caption'] }}</div>@endif
            </td>
            <td class="r-d amt">{{ $d ? Money::format($d['amount']) : '' }}</td>
        </tr>
    @endfor
    <tr class="total">
        <td class="t t-e l-e">Total Penghasilan Bruto (A)</td>
        <td class="t t-e r-e right green">{{ Money::rupiah($slip['gross']) }}</td>
        <td class="gap"></td>
        <td class="t t-d l-d">Total Pemotongan (B)</td>
        <td class="t t-d r-d right red">{{ Money::rupiah($slip['total_deductions']) }}</td>
    </tr>
</table>

<table class="thp">
    <tr>
        <td style="width:62%">
            <div class="title">TAKE HOME PAY (GAJI BERSIH DITERIMA)</div>
            <div class="words">&ldquo;{{ $slip['terbilang'] }}&rdquo;</div>
        </td>
        <td style="width:38%">
            <div class="amount">{{ Money::rupiah($slip['thp']) }}</div>
            <div class="calc">(Penerimaan {{ Money::rupiah($slip['gross']) }} &minus; Potongan {{ Money::rupiah($slip['total_deductions']) }})</div>
        </td>
    </tr>
</table>

<table class="info">
    <tr>
        <td class="cell" style="width:58%">
            <div class="h">INFORMASI PEMBAYARAN / TRANSFER</div>
            <div class="bank">{{ $slip['bank_label'] }}</div>
            <div class="txt">Atas Nama: <span class="b">{{ $slip['account_name'] }}</span> • Tgl Pembayaran: {{ $slip['payment_date'] }}</div>
        </td>
        <td style="width:2%"></td>
        <td class="cell" style="width:40%">
            <div class="h">PEMBERITAHUAN KEAMANAN DOKUMEN</div>
            <div class="txt">Dokumen ini diterbitkan secara sah oleh HRIS Rumatku • ROSY. Dilindungi kata sandi 6 digit tanggal lahir (DDMMYY) saat diakses via aplikasi Rumatku.</div>
        </td>
    </tr>
</table>

<table class="sign">
    <tr>
        <td class="cell" style="width:49%">
            <div class="caption">Diterima oleh Karyawan,</div>
            <div class="line"></div>
            <div class="name">{{ $slip['employee_name'] }}</div>
            <div class="role">Tanggal Terima: [Sesuai Notifikasi App]</div>
        </td>
        <td style="width:2%"></td>
        <td class="cell" style="width:49%">
            <div class="caption">Disetujui &amp; Diproses oleh,</div>
            <div class="line"></div>
            <div class="name">{{ $slip['signer_name'] }}</div>
            <div class="role">{{ $slip['signer_title'] }}</div>
        </td>
    </tr>
</table>
</body>
</html>
