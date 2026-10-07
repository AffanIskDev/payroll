<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Saldo awal kumulatif pajak (YTD) dari sistem lama, dipakai rekonsiliasi
 * PPh 21 masa pajak terakhir (Pasal 17 UU HPP) dan Formulir 1721-A1.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('employee_tax_initial_balances', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->constrained('employees')->cascadeOnDelete();
            $table->year('tax_year');
            $table->unsignedTinyInteger('cutoff_month')->comment('1 s/d 11: bulan terakhir yang tercakup');
            $table->string('ptkp_status', 10);
            $table->decimal('gross_income_ytd', 15, 2)->default(0);
            $table->decimal('employee_jht_jp_ytd', 15, 2)->default(0);
            $table->decimal('biaya_jabatan_ytd', 15, 2)->default(0);
            $table->decimal('pph21_paid_ytd', 15, 2)->default(0);
            $table->text('notes')->nullable();
            $table->timestamps();

            $table->unique(['employee_id', 'tax_year'], 'uq_emp_tax_year');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('employee_tax_initial_balances');
    }
};
