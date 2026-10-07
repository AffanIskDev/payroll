<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Master karyawan. Di produksi data ini milik ROSY (HAM); di prototipe ini
 * disimpan lokal supaya modul payroll bisa berjalan mandiri.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('employees', function (Blueprint $table) {
            $table->id();
            $table->string('nik', 50)->unique()->comment('NIK / Employee ID ROSY');
            $table->string('full_name', 150);
            $table->string('email', 150)->nullable();
            $table->string('phone', 30)->nullable();
            $table->date('birth_date')->comment('Sumber password PDF slip (DDMMYY)');
            $table->enum('gender', ['L', 'P']);
            $table->string('ptkp_status', 10)->comment('TK/0 .. K/3');
            $table->string('npwp', 30)->nullable();
            $table->string('national_id', 20)->nullable()->comment('NIK KTP 16 digit');
            $table->string('address', 255)->nullable();
            $table->string('department', 100);
            $table->string('position', 100);
            $table->string('employment_status', 30)->default('PKWTT (Tetap)');
            $table->boolean('is_management')->default(false)->comment('Gaji tidak terlihat oleh Staff HRD');
            $table->foreignId('supervisor_id')->nullable()->constrained('employees')->nullOnDelete();
            $table->date('join_date');
            $table->date('resign_date')->nullable();
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('employees');
    }
};
