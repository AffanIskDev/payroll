<?php

namespace Tests;

use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Support\Facades\Storage;

abstract class TestCase extends BaseTestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        // PDF slip, dokumen pajak, dan unggahan impor ditulis ke disk palsu, bukan storage/app.
        Storage::fake(config('payroll.disk'));
        Storage::fake('local');
    }
}
