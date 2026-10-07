@php
    use App\Support\Money;
    $fontDir = resource_path('fonts');
    $l = $r['lines'];
    $amount = fn (int $n) => $n < 0 ? '('.Money::format(-$n).')' : Money::format($n);
@endphp
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Formulir 1721-A1 {{ $r['tax_year'] }}</title>
<style>
    @font-face { font-family: 'Roboto'; font-weight: 400; src: url('{{ $fontDir }}/Roboto-Regular.ttf') format('truetype'); }
    @font-face { font-family: 'Roboto'; font-weight: 700; src: url('{{ $fontDir }}/Roboto-Bold.ttf') format('truetype'); }
    @font-face { font-family: 'Roboto'; font-style: italic; font-weight: 400; src: url('{{ $fontDir }}/Roboto-Italic.ttf') format('truetype'); }
    @page { margin: 22pt 32pt 32pt 32pt; }
    body { font-family: 'Roboto', sans-serif; font-size: 7.5pt; color: #111827; line-height: 1.12; }
    table { border-collapse: collapse; width: 100%; }
    td { vertical-align: top; }
    .head td { border: 1pt solid #111827; padding: 4pt 8pt; vertical-align: middle; }
    .form-code { font-size: 13pt; font-weight: 700; text-align: center; }
    .form-title { font-size: 7.8pt; font-weight: 700; text-align: center; line-height: 1.3; }
    .year { text-align: center; font-size: 8pt; }
    .year b { font-size: 12pt; display: block; }
    .meta { margin-top: 4pt; border: 1pt solid #111827; }
    .meta td { padding: 3pt 8pt; font-size: 7.5pt; }
    .section { margin-top: 6pt; background: #111827; color: #fff; font-weight: 700; font-size: 7.5pt; padding: 3pt 8pt; letter-spacing: 0.3pt; }
    .ident td { border: 0.6pt solid #9ca3af; padding: 1.8pt 7pt; }
    .ident .k { width: 17%; color: #374151; background: #f9fafb; }
    .ident .v { font-weight: 700; }
    .calc td { border: 0.6pt solid #9ca3af; padding: 1.8pt 7pt; }
    .calc .no { width: 22pt; text-align: center; color: #374151; }
    .calc .amt { width: 110pt; text-align: right; font-weight: 700; white-space: nowrap; }
    .calc .sub td { background: #f3f4f6; font-weight: 700; font-size: 7.1pt; letter-spacing: 0.2pt; }
    .calc .total td { background: #eef2ff; }
    .note { margin-top: 4pt; font-size: 6.8pt; color: #4b5563; }
    .warn { margin-top: 4pt; border: 0.8pt solid #f59e0b; background: #fffbeb; color: #92400e; padding: 3pt 8pt; font-size: 7pt; }
    .sign td { padding: 3pt 8pt; }
    .sign .box { border: 0.8pt solid #9ca3af; height: 42pt; text-align: center; vertical-align: bottom; padding-bottom: 5pt; }
    .watermark { position: fixed; top: 330pt; left: 0; right: 0; text-align: center; font-size: 70pt; font-weight: 700; color: #94a3b8; opacity: 0.13; transform: rotate(-28deg); }
    .footer { position: fixed; bottom: -18pt; left: 0; right: 0; font-size: 6.8pt; color: #6b7280; border-top: 0.6pt solid #d1d5db; padding-top: 3pt; }
</style>
</head>
<body>
@unless ($r['is_final'])
    <div class="watermark">SEMENTARA</div>
@endunless
<div class="footer">
    Dokumen pendamping internal HRIS ROSY • Bukti pemotongan resmi diterbitkan melalui Coretax DJP • Dicetak {{ $printedAt }}
</div>

<table class="head">
    <tr>
        <td style="width:22%"><div class="form-code">FORMULIR<br>1721 - A1</div></td>
        <td style="width:56%"><div class="form-title">BUKTI PEMOTONGAN PAJAK PENGHASILAN PASAL 21 BAGI PEGAWAI TETAP ATAU PENERIMA PENSIUN ATAU TUNJANGAN HARI TUA/JAMINAN HARI TUA BERKALA</div></td>
        <td style="width:22%"><div class="year">TAHUN PAJAK<b>{{ $r['tax_year'] }}</b></div></td>
    </tr>
</table>
<table class="meta">
    <tr>
        <td>NOMOR: <b>{{ $r['number'] }}</b></td>
        <td style="text-align:right">MASA PEROLEHAN PENGHASILAN: <b>{{ sprintf('%02d', $r['period_from']) }} – {{ sprintf('%02d', $r['period_to']) }}</b> ({{ $monthNames[$r['period_from']] }} s.d. {{ $monthNames[$r['period_to']] }} {{ $r['tax_year'] }})</td>
    </tr>
</table>

<div class="section">A. IDENTITAS PEMOTONG PAJAK</div>
<table class="ident">
    <tr><td class="k">1. NPWP Pemotong</td><td class="v">{{ $r['employer']['npwp'] }}</td><td class="k">2. Nama Pemotong</td><td class="v">{{ $r['employer']['name'] }}</td></tr>
    <tr><td class="k">3. Alamat</td><td class="v" colspan="3">{{ $r['employer']['address'] }}</td></tr>
</table>

<div class="section">B. IDENTITAS PENERIMA PENGHASILAN YANG DIPOTONG</div>
<table class="ident">
    <tr><td class="k">1. NPWP</td><td class="v">{{ $r['employee']['npwp'] ?: '— (memakai NIK)' }}</td><td class="k">2. NIK (KTP)</td><td class="v">{{ $r['employee']['national_id'] ?: '-' }}</td></tr>
    <tr><td class="k">3. Nama</td><td class="v">{{ $r['employee']['name'] }} <span style="font-weight:400;color:#6b7280">({{ $r['employee']['nik'] }})</span></td><td class="k">4. Jenis Kelamin</td><td class="v">{{ $r['employee']['gender'] }}</td></tr>
    <tr><td class="k">5. Alamat</td><td class="v">{{ $r['employee']['address'] ?: '-' }}</td><td class="k">6. Status PTKP</td><td class="v">{{ $r['employee']['ptkp_status'] }}</td></tr>
    <tr><td class="k">7. Nama Jabatan</td><td class="v">{{ $r['employee']['position'] }}</td><td class="k">8. Karyawan Asing</td><td class="v">Tidak</td></tr>
</table>

<div class="section">C. RINCIAN PENGHASILAN DAN PENGHITUNGAN PPh PASAL 21 &nbsp;•&nbsp; KODE OBJEK PAJAK 21-100-01</div>
<table class="calc">
    <tr class="sub"><td colspan="3">PENGHASILAN BRUTO</td></tr>
    @foreach (range(1, 22) as $no)
        @if ($no === 9)<tr class="sub"><td colspan="3">PENGURANGAN</td></tr>@endif
        @if ($no === 13)<tr class="sub"><td colspan="3">PENGHITUNGAN PPh PASAL 21</td></tr>@endif
        <tr class="{{ in_array($no, [8, 12, 13, 17, 20, 22], true) ? 'total' : '' }}">
            <td class="no">{{ $no }}</td>
            <td>{{ $lineLabels[$no] }}</td>
            <td class="amt">{{ $amount($l[$no]) }}</td>
        </tr>
    @endforeach
</table>

@if ($r['source']['initial_balance'])
    <div class="note">Baris 1 termasuk saldo awal YTD hasil impor sistem lama (Januari s.d. {{ $monthNames[$r['source']['initial_balance']['cutoff_month']] }}) sebesar Rp {{ Money::format($r['source']['initial_balance']['gross']) }} yang tidak dirinci per komponen; baris 21 termasuk PPh 21 saldo awal Rp {{ Money::format($r['source']['initial_balance']['pph21']) }}.</div>
@endif
@foreach ($r['warnings'] as $warning)
    <div class="warn">{{ $warning }}</div>
@endforeach

<div class="section">TANDA TANGAN PEMOTONG / KUASA</div>
<table class="sign">
    <tr>
        <td style="width:55%; font-size:7.6pt; color:#374151">
            Dengan ini menyatakan bahwa bukti pemotongan ini diisi dengan benar dan lengkap sesuai data penggajian HRIS ROSY.<br><br>
            Tanggal: <b>{{ $printedAt }}</b>
        </td>
        <td style="width:45%">
            <div class="box">
                <b>{{ $r['employer']['signer'] }}</b><br>
                <span style="color:#6b7280">{{ $r['employer']['signer_title'] }}</span>
            </div>
        </td>
    </tr>
</table>
</body>
</html>
