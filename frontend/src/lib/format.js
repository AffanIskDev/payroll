export const rp = (v) => "Rp " + Math.round(Number(v) || 0).toLocaleString("id-ID");

// Jam lembur desimal → "25 jam 58 menit" (short: "25 j 58 m"). Lembur dibayar per menit seperti rekap Excel
// lembur driver (keputusan user 11 Okt 2026), jadi jamnya tidak lagi selalu .0/.5.
export const jamMenit = (hours, short = false) => {
  const total = Math.round((Number(hours) || 0) * 60);
  const [j, m] = [Math.floor(total / 60), total % 60];
  const [uj, um] = short ? ["j", "m"] : ["jam", "menit"];
  if (j && m) return `${j} ${uj} ${m} ${um}`;
  return j ? `${j} ${uj}` : `${m} ${um}`;
};

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

// "2026-10-01" → "1 Oktober 2026"
export const formatDate = (iso) =>
  iso ? `${Number(iso.slice(8, 10))} ${BULAN[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}` : "-";

// Rentang periode: "1–30 September 2026"; lintas bulan "26 Agustus – 25 September 2026"; lintas tahun lengkap keduanya
export const formatDateRange = (start, end) => {
  if (!start || !end) return "-";
  if (start === end) return formatDate(start);
  const month = BULAN[Number(start.slice(5, 7)) - 1];
  if (start.slice(0, 7) === end.slice(0, 7)) return `${Number(start.slice(8, 10))}–${formatDate(end)}`;
  if (start.slice(0, 4) === end.slice(0, 4)) return `${Number(start.slice(8, 10))} ${month} – ${formatDate(end)}`;
  return `${formatDate(start)} – ${formatDate(end)}`;
};

// "9 Okt 2026, 11.05"
export const formatDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("id-ID", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";

// "baru saja" / "25 menit lalu" / "3 jam lalu" / "kemarin" / "3 hari lalu" — dihitung per tanggal kalender
export const timeAgo = (iso, now = new Date()) => {
  const t = new Date(iso);
  const min = Math.floor((now - t) / 60000);
  if (min < 1) return "baru saja";
  if (min < 60) return `${min} menit lalu`;
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(t.getFullYear(), t.getMonth(), t.getDate())) / 86400000);
  if (days < 1) return `${Math.floor(min / 60)} jam lalu`;
  return days === 1 ? "kemarin" : `${days} hari lalu`;
};

// Tanggal lokal (zona waktu peramban HRD) sebagai "YYYY-MM-DD"
export const localIso = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

// Sinkron selagi periode berjalan ikut membawa absensi hari itu yang belum selesai (user 12 Okt 2026): HAM menghitung
// sampai hari ini, jadi karyawan yang belum absen masuk saat sinkron terbaca alfa. Tanggal hari itu bila kena, selain itu null.
export const unfinishedSyncDay = (start, end, at = new Date()) => {
  const day = localIso(at);
  return start && end && start <= day && day <= end ? day : null;
};

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
