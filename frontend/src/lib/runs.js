// Jenis run payroll (user 30 Okt 2026): Gaji = siklus bulanan; THR & Bonus Tahunan = run sendiri di luar gaji, dibayar
// di tanggalnya sendiri. Satu tempat untuk nama dan alamat halamannya, dipakai menu, daftar, dan tautan notifikasi.
export const RUNS = {
  gaji: { key: "gaji", label: "Gaji", base: "/hr-manager/payroll" },
  thr: { key: "thr", label: "THR", base: "/hr-manager/payroll/thr", titleHint: "Idul Fitri 1448 H" },
  bonus_tahunan: { key: "bonus_tahunan", label: "Bonus Tahunan", base: "/hr-manager/payroll/bonus-tahunan", titleHint: "2026" },
};

export const runPath = (runType, pid) => {
  const base = (RUNS[runType] || RUNS.gaji).base;
  return pid ? `${base}/${pid}` : base;
};
