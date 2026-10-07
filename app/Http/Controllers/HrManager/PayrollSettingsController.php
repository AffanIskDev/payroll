<?php

namespace App\Http\Controllers\HrManager;

use App\Http\Controllers\Controller;
use App\Models\PayrollConfig;
use App\Services\Payroll\PayrollSettings;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;
use Illuminate\View\View;

class PayrollSettingsController extends Controller
{
    public function edit(PayrollSettings $settings): View
    {
        return view('hr-manager.payroll.settings', [
            'definitions' => PayrollConfig::DEFINITIONS,
            'values' => $settings->all(),
            'updatedAt' => PayrollConfig::query()->pluck('updated_at', 'config_key'),
        ]);
    }

    public function update(Request $request, PayrollSettings $settings): RedirectResponse
    {
        $rules = [];
        $names = [];
        foreach (PayrollConfig::DEFINITIONS as $key => $def) {
            $names["configs.{$key}"] = $def['label'];
            $rules["configs.{$key}"] = match ($def['type']) {
                'money' => ['required', 'integer', 'min:0', 'max:1000000000'],
                'int' => ['required', 'integer', 'min:1', 'max:31'],
                'json' => ['required', 'string', 'max:255', 'json', function ($attr, $value, $fail) {
                    $tiers = json_decode($value, true);
                    if (! is_array($tiers) || collect($tiers)->contains(fn ($t) => ! is_array($t) || ! isset($t['min'], $t['amount'])
                        || ! is_numeric($t['min']) || ! is_numeric($t['amount']))) {
                        $fail('Format harus daftar {"min": skor, "amount": nominal}.');
                    }
                }],
                'enum' => ['required', Rule::in(array_keys($def['options']))],
                default => ['required', 'string', 'max:255'],
            };
        }

        $data = $request->validate($rules, [], $names)['configs'];

        foreach (PayrollConfig::DEFINITIONS as $key => $def) {
            PayrollConfig::updateOrCreate(
                ['config_key' => $key],
                ['config_value' => (string) $data[$key], 'description' => $def['description']],
            );
        }
        $settings->flush();

        return back()->with('status', 'Pengaturan payroll disimpan. Nilai baru berlaku untuk generate / hitung ulang slip draft berikutnya.');
    }
}
