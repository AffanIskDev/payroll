<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('payroll_periods', function (Blueprint $table) {
            $table->id();
            $table->string('period_code', 7)->unique()->comment('YYYY-MM');
            $table->string('period_name', 50);
            $table->date('start_date');
            $table->date('end_date');
            $table->date('payment_date');
            $table->enum('status', ['draft', 'locked', 'published', 'closed'])->default('draft');

            // Progres batch generate (ProcessMonthlyPayrollJob).
            $table->enum('generation_status', ['idle', 'queued', 'running', 'completed', 'failed'])->default('idle');
            $table->unsignedInteger('generation_total')->default(0);
            $table->unsignedInteger('generation_processed')->default(0);
            $table->text('generation_error')->nullable();
            $table->timestamp('generated_at')->nullable();

            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('approved_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('approved_at')->nullable();
            $table->timestamp('published_at')->nullable();
            $table->timestamp('closed_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('payroll_periods');
    }
};
