export const rp = (v) => "Rp " + Math.round(Number(v) || 0).toLocaleString("id-ID");

export const LEAVE_LABELS = {
  present: "Hadir",
  sick_with_certificate: "Sakit (SKD)",
  annual_leave: "Cuti Tahunan",
  statutory_leave: "Cuti Khusus",
  maternity_leave: "Cuti Melahirkan",
  religious_leave: "Cuti Ibadah",
  menstrual_leave: "Cuti Haid",
  approved_unpaid_leave: "Izin Tanpa Upah",
  permission_leave: "Izin",
  official_duty: "Dinas Luar",
  dispensation: "Dispensasi",
  day_off: "Libur",
  alpha: "Mangkir (Alpha)",
};

// Nama periode otomatis bila mulai & selesai di bulan yang sama (aturan yang sama dengan backend periods.py)
const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
  "November", "Desember"];
export const periodNameFor = (start, end) =>
  start && end && start.slice(0, 7) === end.slice(0, 7) ? `${BULAN[Number(start.slice(5, 7)) - 1]} ${start.slice(0, 4)}` : null;

// data_issues from HAM's payroll feed (PayrollFeedRules::masalahData)
export const DATA_ISSUE_LABELS = {
  npwp_kosong: "NPWP kosong",
  npwp_format_salah: "NPWP salah format",
  tgl_lahir_kosong_atau_tidak_terbaca: "Tgl lahir kosong",
  tgl_lahir_tidak_wajar: "Tgl lahir tidak wajar",
  rekening_kosong: "Rekening kosong",
  belum_tertaut_rumatku: "Belum tertaut RUMATKU",
  gaji_pokok_nol: "Gaji pokok 0",
  lembur_tanpa_tarif: "Akses lembur tanpa tarif",
};

export const PAYROLL_STATUS_LABELS = {
  active: "Aktif",
  unpaid_leave: "Cuti di Luar Tanggungan",
  prolonged_illness: "Sakit Berkepanjangan",
  work_accident_stmb: "Kecelakaan Kerja (STMB)",
};

export const PERIOD_STATUS = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  pending_approval: { label: "Menunggu Approval", cls: "bg-amber-50 text-amber-700 border-amber-300" },
  revision: { label: "Ditolak · Revisi", cls: "bg-rose-50 text-rose-700 border-rose-300" },
  approved: { label: "Approved & Locked", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
  closed: { label: "Closed", cls: "bg-purple-50 text-purple-700 border-purple-300" },
};

export const DELIVERY_STATUS = {
  queued: { label: "Mengirim...", cls: "bg-blue-50 text-blue-700 border-blue-300" },
  sent: { label: "Terkirim", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
  failed: { label: "Gagal", cls: "bg-rose-50 text-rose-700 border-rose-300" },
};

export const SLIP_STATUS = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  approved: { label: "Locked", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
};
