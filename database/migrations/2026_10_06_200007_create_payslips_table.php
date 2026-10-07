<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Snapshot final penggajian per karyawan per periode. Identitas, profil gaji,
 * dan rekening disalin ke sini supaya slip yang sudah terbit tidak berubah
 * walau master data berubah.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('payslips', function (Blueprint $table) {
            $table->id();
            $table->foreignId('payroll_period_id')->constrained('payroll_periods')->cascadeOnDelete();
            $table->foreignId('employee_id')->constrained('employees')->restrictOnDelete();
            $table->enum('status', ['draft', 'locked', 'published'])->default('draft');

            // Snapshot identitas & status pajak
            $table->string('employee_nik', 50);
            $table->string('employee_name', 150);
            $table->string('department', 100)->nullable();
            $table->string('position', 100)->nullable();
            $table->string('employment_status', 30)->nullable();
            $table->string('ptkp_status', 10);
            $table->char('ter_category', 1)->nullable();
            $table->decimal('ter_rate', 6, 4)->nullable()->comment('Persen, mis. 1.5000');

            // Dasar upah
            $table->decimal('basic_salary', 15, 2);
            $table->decimal('position_allowance', 15, 2)->default(0);
            $table->decimal('attendance_allowance', 15, 2)->default(0);
            $table->decimal('bpjs_kes_base_salary', 15, 2)->default(0);
            $table->decimal('bpjs_tk_base_salary', 15, 2)->default(0);
            $table->decimal('bpjs_jp_base_salary', 15, 2)->default(0);
            $table->decimal('jkk_rate', 5, 4)->default(0.0024);

            // Kehadiran & penalti keterlambatan
            $table->unsignedTinyInteger('attended_days')->default(0);
            $table->unsignedTinyInteger('leave_sick_days')->default(0);
            $table->unsignedTinyInteger('absent_days')->default(0);
            $table->unsignedInteger('late_minutes_total')->default(0);
            $table->unsignedSmallInteger('late_count_15')->default(0);
            $table->unsignedSmallInteger('late_days_60')->default(0);
            $table->integer('late_penalty_days')->default(0);
            $table->string('late_penalty_rule', 30)->nullable();
            $table->decimal('late_penalty_amount', 15, 2)->default(0);

            // Penerimaan
            $table->decimal('overtime_hours', 5, 2)->default(0);
            $table->decimal('overtime_rate', 15, 2)->default(0);
            $table->decimal('overtime_pay', 15, 2)->default(0);
            $table->decimal('kpi_score', 5, 2)->nullable();
            $table->decimal('kpi_incentive', 15, 2)->default(0);
            $table->decimal('additional_bonus', 15, 2)->default(0);
            $table->decimal('tunjangan_bpjs_kes', 15, 2)->default(0);
            $table->decimal('tunjangan_bpjs_tk', 15, 2)->default(0);
            $table->decimal('gross_earnings', 15, 2)->default(0);

            // Potongan
            $table->decimal('iuran_bpjs_kes_total', 15, 2)->default(0);
            $table->decimal('iuran_bpjs_tk_total', 15, 2)->default(0);
            $table->decimal('employee_jht_jp', 15, 2)->default(0)->comment('Porsi pekerja JHT 2% + JP 1%, pengurang PPh tahunan');
            $table->json('bpjs_breakdown')->nullable();
            $table->decimal('pph21_amount', 15, 2)->default(0)->comment('Negatif = pengembalian lebih potong (Desember)');
            $table->string('pph21_method', 20)->default('TER');
            $table->json('pph21_breakdown')->nullable();
            $table->decimal('other_deductions', 15, 2)->default(0)->comment('Kasbon / lain-lain');
            $table->text('other_deductions_note')->nullable();
            $table->decimal('total_deductions', 15, 2)->default(0);

            // Hasil akhir
            $table->decimal('take_home_pay', 15, 2)->default(0);
            $table->text('terbilang');
            $table->string('bank_name', 50);
            $table->string('bank_account_number', 50);
            $table->string('bank_account_name', 100)->nullable();

            // Penyesuaian manual Manager HRD
            $table->json('system_values')->nullable()->comment('Nilai hasil hitung sistem untuk kolom yang bisa di-override');
            $table->json('overrides')->nullable()->comment('Nilai manual Manager HRD');
            $table->boolean('is_manually_adjusted')->default(false);
            $table->text('adjustment_notes')->nullable();

            // PDF & publikasi
            $table->string('pdf_path', 255)->nullable();
            $table->string('pdf_password_hash', 255)->nullable();
            $table->timestamp('pdf_generated_at')->nullable();
            $table->string('pdf_error', 500)->nullable()->comment('Galat terakhir pembuatan PDF');
            $table->foreignId('locked_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('locked_at')->nullable();
            $table->timestamp('published_at')->nullable();
            $table->timestamps();

            $table->unique(['payroll_period_id', 'employee_id'], 'uq_period_emp');
            $table->index(['employee_id', 'status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('payslips');
    }
};
