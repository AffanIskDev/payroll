<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Tabel sumber data payroll. Di produksi data ini ditarik dari Rumatku
 * (presensi & lembur) dan ROSY (skor KPI, kasbon); di prototipe disimpan lokal
 * dan dibaca lewat App\Services\Payroll\Contracts\PayrollDataSource.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('attendance_logs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->constrained('employees')->cascadeOnDelete();
            $table->date('work_date');
            $table->enum('status', ['HADIR', 'IZIN', 'SAKIT', 'CUTI', 'ALPA']);
            $table->time('scheduled_start')->nullable();
            $table->time('check_in_at')->nullable();
            $table->time('check_out_at')->nullable();
            $table->unsignedInteger('late_minutes')->default(0);
            $table->string('source', 20)->default('RUMATKU');
            $table->timestamps();

            $table->unique(['employee_id', 'work_date']);
        });

        Schema::create('overtime_records', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->constrained('employees')->cascadeOnDelete();
            $table->date('work_date');
            $table->decimal('hours', 5, 2);
            $table->enum('status', ['PENDING', 'APPROVED', 'REJECTED'])->default('APPROVED');
            $table->string('notes', 255)->nullable();
            $table->string('source', 20)->default('RUMATKU');
            $table->timestamps();

            $table->index(['employee_id', 'work_date']);
        });

        Schema::create('kpi_scores', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->constrained('employees')->cascadeOnDelete();
            $table->string('period_code', 7);
            $table->decimal('score', 5, 2);
            $table->decimal('incentive_amount', 15, 2)->nullable()->comment('Kalau ROSY sudah memberi nominal');
            $table->foreignId('confirmed_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('confirmed_at')->nullable();
            $table->string('source', 20)->default('ROSY');
            $table->timestamps();

            $table->unique(['employee_id', 'period_code']);
        });

        Schema::create('employee_loans', function (Blueprint $table) {
            $table->id();
            $table->foreignId('employee_id')->constrained('employees')->cascadeOnDelete();
            $table->string('description', 150);
            $table->decimal('installment_amount', 15, 2);
            $table->string('start_period', 7)->comment('YYYY-MM cicilan pertama');
            $table->unsignedSmallInteger('installments_total');
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::create('payroll_exports', function (Blueprint $table) {
            $table->id();
            $table->foreignId('payroll_period_id')->constrained('payroll_periods')->cascadeOnDelete();
            $table->foreignId('user_id')->nullable()->constrained('users')->nullOnDelete();
            $table->string('bank', 20)->default('BSI');
            $table->string('debit_account', 50);
            $table->date('effective_date');
            $table->string('file_name', 255);
            $table->unsignedInteger('row_count');
            $table->decimal('total_amount', 17, 2);
            $table->timestamps();
        });

        // Penanda per slip agar file transfer bank tidak memuat slip yang sama dua kali.
        Schema::table('payslips', function (Blueprint $table) {
            $table->foreignId('payroll_export_id')->nullable()->after('published_at')
                ->constrained('payroll_exports')->nullOnDelete();
            $table->timestamp('bsi_exported_at')->nullable()->after('payroll_export_id');
        });
    }

    public function down(): void
    {
        Schema::table('payslips', function (Blueprint $table) {
            $table->dropConstrainedForeignId('payroll_export_id');
            $table->dropColumn('bsi_exported_at');
        });
        Schema::dropIfExists('payroll_exports');
        Schema::dropIfExists('employee_loans');
        Schema::dropIfExists('kpi_scores');
        Schema::dropIfExists('overtime_records');
        Schema::dropIfExists('attendance_logs');
    }
};
