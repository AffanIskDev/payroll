@props(['status', 'label' => null])
@php
    $labels = [
        'draft' => 'Draft - Menunggu Approval',
        'locked' => 'Terkunci - Memproses PDF',
        'published' => 'Published',
        'closed' => 'Ditutup',
    ];
@endphp
<span {{ $attributes->class(['badge', 'badge-'.$status]) }}>
    @if ($status === 'locked')
        <svg class="size-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" class="opacity-25"/><path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
    @elseif ($status === 'published')
        <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>
    @endif
    {{ $label ?? ($labels[$status] ?? $status) }}
</span>
