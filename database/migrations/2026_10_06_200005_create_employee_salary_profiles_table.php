<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('employee_salary_profiles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->unique()->constrained('employees')->cascadeOnDelete();
            $table->decimal('basic_salary', 15, 2);
            $table->decimal('position_allowance', 15, 2)->default(0);
            $table->decimal('monthly_attendance_allowance', 15, 2)->default(0);
            $table->decimal('overtime_hourly_rate', 15, 2)->default(0);

            // Checklist kepesertaan BPJS per program (PRD 3.4 butir 4).
            $table->boolean('has_bpjs_kes')->default(true);
            $table->boolean('has_jkk')->default(true);
            $table->boolean('has_jkm')->default(true);
            $table->boolean('has_jht')->default(true);
            $table->boolean('has_jp')->default(true);
            $table->decimal('jkk_rate', 5, 4)->default(0.0024)->comment('Tingkat risiko JKK, default 0,24%');

            $table->string('bank_name', 50);
            $table->string('bank_account_number', 50);
            $table->string('bank_account_name', 100)->nullable()->comment('Nama sesuai rekening');
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('employee_salary_profiles');
    }
};
