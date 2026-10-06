export const rp = (v) => "Rp " + Math.round(Number(v) || 0).toLocaleString("id-ID");

export const LEAVE_LABELS = {
  present: "Hadir",
  sick_with_certificate: "Sakit (SKD)",
  annual_leave: "Cuti Tahunan",
  statutory_leave: "Izin Normatif",
  maternity_leave: "Cuti Melahirkan",
  menstrual_leave: "Cuti Haid",
  approved_unpaid_leave: "Izin Tanpa Upah",
  alpha: "Mangkir (Alpha)",
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
  approved: { label: "Approved & Locked", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
  closed: { label: "Closed", cls: "bg-purple-50 text-purple-700 border-purple-300" },
};

export const SLIP_STATUS = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  approved: { label: "Locked", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
};
