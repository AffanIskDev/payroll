<?php

namespace App\Http\Controllers\HrManager;

use App\Exports\TaxInitialBalanceTemplateExport;
use App\Http\Controllers\Controller;
use App\Imports\EmployeeTaxInitialBalanceImport;
use App\Models\EmployeeTaxInitialBalance;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Illuminate\View\View;
use Maatwebsite\Excel\Facades\Excel;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

/** Modul 4A: unggah saldo awal pajak YTD dengan validasi sebelum simpan. */
class TaxInitialBalanceImportController extends Controller
{
    private const SESSION_KEY = 'ytd_import_file';

    private const DISK = 'local';

    public function create(Request $request): View
    {
        $balances = EmployeeTaxInitialBalance::query()->with('employee:id,nik,full_name')
            ->orderByDesc('tax_year')->orderBy('employee_id')->get();

        return view('hr-manager.payroll.import-ytd', [
            'balances' => $balances,
            'result' => session('ytd_result'),
        ]);
    }

    public function template(): BinaryFileResponse
    {
        return Excel::download(new TaxInitialBalanceTemplateExport, 'template_saldo_awal_pajak_ytd.xlsx');
    }

    /** Langkah 1: unggah & validasi format; belum ada data yang disimpan. */
    public function check(Request $request): RedirectResponse
    {
        $request->validate([
            'file' => ['required', 'file', 'max:5120', function (string $attribute, $file, \Closure $fail) {
                if (! in_array(strtolower($file->getClientOriginalExtension()), ['xlsx', 'xls', 'csv'], true)) {
                    $fail('File saldo awal harus berformat .xlsx, .xls, atau .csv.');
                }
            }],
        ], [], ['file' => 'file saldo awal']);

        $this->forgetPending($request);

        $file = $request->file('file');
        $extension = strtolower($file->getClientOriginalExtension());
        $path = $file->storeAs('imports/ytd', Str::uuid().'.'.$extension, self::DISK);
        $absolute = Storage::disk(self::DISK)->path($path);

        $import = $this->runImport($absolute, $extension, dryRun: true);
        $request->session()->put(self::SESSION_KEY, ['path' => $path, 'extension' => $extension, 'name' => $file->getClientOriginalName()]);

        return redirect()->route('hr-manager.payroll.import-ytd')->with('ytd_result', [
            'file' => $file->getClientOriginalName(),
            'total' => $import->total,
            'valid' => $import->valid,
            'errors' => $import->errors,
            'warnings' => $import->warnings,
            'can_commit' => $import->total > 0 && ! $import->errors,
        ]);
    }

    /** Langkah 2: simpan. File divalidasi ulang; seluruh baris harus lolos. */
    public function commit(Request $request): RedirectResponse
    {
        $pending = $request->session()->get(self::SESSION_KEY);
        if (! $pending || ! Storage::disk(self::DISK)->exists($pending['path'])) {
            return redirect()->route('hr-manager.payroll.import-ytd')->with('error', 'Unggah dan validasi file terlebih dahulu.');
        }

        $absolute = Storage::disk(self::DISK)->path($pending['path']);
        $check = $this->runImport($absolute, $pending['extension'], dryRun: true);
        if ($check->errors || $check->total === 0) {
            return redirect()->route('hr-manager.payroll.import-ytd')->with('error', 'File tidak lolos validasi ulang; tidak ada data yang disimpan.');
        }

        $save = $this->runImport($absolute, $pending['extension'], dryRun: false);
        $this->forgetPending($request);

        return redirect()->route('hr-manager.payroll.import-ytd')
            ->with('status', "{$save->saved} saldo awal pajak dari {$pending['name']} tersimpan (updateOrCreate per NIK + tahun pajak).");
    }

    private function runImport(string $absolute, string $extension, bool $dryRun): EmployeeTaxInitialBalanceImport
    {
        $import = new EmployeeTaxInitialBalanceImport(
            dryRun: $dryRun,
            delimiter: $extension === 'csv' ? EmployeeTaxInitialBalanceImport::detectDelimiter($absolute) : ',',
        );
        $readerType = match ($extension) {
            'csv' => \Maatwebsite\Excel\Excel::CSV,
            'xls' => \Maatwebsite\Excel\Excel::XLS,
            default => \Maatwebsite\Excel\Excel::XLSX,
        };
        Excel::import($import, $absolute, null, $readerType);

        return $import;
    }

    private function forgetPending(Request $request): void
    {
        $pending = $request->session()->pull(self::SESSION_KEY);
        if ($pending) {
            Storage::disk(self::DISK)->delete($pending['path']);
        }
    }
}
