<x-layouts.app :title="'Workbench · '.$payslip->employee_name">
    <livewire:payroll-workbench
        :payslip="$payslip"
        :prev-employee-id="$prev"
        :next-employee-id="$next"
        :position-label="'Karyawan '.($position + 1).' dari '.$ids->count()" />
</x-layouts.app>
