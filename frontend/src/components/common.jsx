import { Search, X } from "lucide-react";
import { PERIOD_STATUS } from "@/lib/format";

// Filter Nama (user 21 Okt 2026, menu Pajak): kotak cari di atas tabel; hurufnya tak dibedakan besar-kecil dan tiap kata yang
// diketik harus ada di nama ("budi san" cocok dengan "Budi Santoso"). Penyaringnya dipakai bersama lewat matchName.
export const matchName = (name, query) => {
  const words = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  const hay = String(name || "").toLowerCase();
  return words.every((w) => hay.includes(w));
};

export const NameFilter = ({ value, onChange, testId }) => (
  <label className="flex items-center gap-2 border-2 border-slate-400 rounded-md px-3 py-[7px] bg-white w-full sm:w-56 focus-within:border-brand-700 focus-within:ring-2 focus-within:ring-brand-700/10">
    <Search className="h-4 w-4 text-slate-400 shrink-0" />
    <input data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)} placeholder="Filter Nama..." aria-label="Filter Nama" className="outline-none text-sm w-full bg-transparent" />
    {value && <button type="button" onClick={() => onChange("")} aria-label="Hapus filter nama" data-testid={`${testId}-clear`} className="text-slate-400 hover:text-slate-700"><X className="h-4 w-4" /></button>}
  </label>
);

// Status sebagai LABEL, bukan kotak (user 13 Okt 2026): titik berwarna + teks tanpa bingkai atau latar, kursor panah,
// supaya tidak disangka tombol yang bisa diklik. caption = awalan abu-abu ("Status:"), large = ukuran untuk di samping judul;
// testId menempel pada teks statusnya saja (tanpa awalan)
export const StatusBadge = ({ map, status, testId, caption, large }) => {
  const s = map[status] || { label: status, cls: "text-slate-600", dot: "bg-slate-400" };
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap cursor-default ${large ? "text-base" : "text-sm"}`}>
      {caption && <span className="text-slate-500">{caption}</span>}
      <span data-testid={testId} className={`inline-flex items-center gap-1.5 font-medium ${s.cls}`}>
        <span className={`h-2 w-2 rounded-full shrink-0 ${s.dot}`} aria-hidden="true" />
        {s.label}
      </span>
    </span>
  );
};

// titleExtra = keterangan di samping judul (mis. "Status: Draft" di halaman periode, user 13 Okt 2026), bukan di deretan tombol
export const PageTitle = ({ title, titleExtra, subtitle, children }) => {
  const h1 = <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">{title}</h1>;
  return (
    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
      <div>
        {titleExtra ? <div className="flex flex-wrap items-center gap-x-4 gap-y-1">{h1}{titleExtra}</div> : h1}
        {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
};

export const Panel = ({ title, right, children, className = "" }) => (
  <section className={`bg-white border border-slate-200 rounded-xl shadow-sm ${className}`}>
    {title && (
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
        <h2 className="text-base font-bold text-slate-900">{title}</h2>
        {right}
      </div>
    )}
    {children}
  </section>
);

// Aksen kartu angka (14 Okt 2026): garis warna di kiri + angka berwarna, supaya tiap kartu langsung terbaca maknanya.
// Warna hanya untuk MAKNA, cukup 4 (keputusan 14 Okt 2026) — jangan menambah warna per jenis angka.
// Kelas ditulis lengkap agar terbaca Tailwind.
export const ACCENTS = {
  brand: { bar: "bg-brand-600", text: "text-brand-700" },       // informasi biasa
  emerald: { bar: "bg-emerald-500", text: "text-emerald-600" }, // baik / selesai
  amber: { bar: "bg-amber-500", text: "text-amber-600" },       // perlu dicek
  rose: { bar: "bg-rose-500", text: "text-rose-600" },          // masalah
};

// isi kartu beraksen; angka 0 ditampilkan abu-abu supaya yang bernilai lebih menonjol
export const AccentBody = ({ icon: Icon, label, value, sub, accent = "brand", dim, big, valueTestId }) => {
  const a = ACCENTS[accent] || ACCENTS.brand;
  // "Rp" dicetak lebih kecil supaya nominal besar muat di kartu yang sempit (sidebar kiri, 14 Okt 2026)
  const rpMatch = typeof value === "string" && value.match(/^(-?)Rp\s?(.*)$/);
  const shown = rpMatch ? <><span className="text-[0.6em] font-bold mr-1 align-[0.12em]">{rpMatch[1]}Rp</span>{rpMatch[2]}</> : value;
  return (
    <>
      <span aria-hidden="true" className={`absolute left-0 inset-y-0 w-1.5 ${a.bar}`} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-600">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-slate-400 shrink-0" />}
      </div>
      <div data-testid={valueTestId} className={`num ${big ? "text-2xl leading-tight mt-2" : "text-2xl mt-1"} font-extrabold whitespace-nowrap ${dim ? "text-slate-400" : a.text}`}>{shown}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </>
  );
};

// kartu ringkasan yang sekaligus menyaring tabel (halaman periode, user 10 Okt 2026; halaman karyawan, 12 Okt);
// kursor di atas kartu menampilkan namanya
export const SummaryCard = ({ icon, label, value, sub, names, accent = "brand", active, onClick, testId }) => {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} onClick={onClick} aria-pressed={onClick ? !!active : undefined} data-testid={testId}
      title={names?.length ? `${names.slice(0, 40).join(", ")}${names.length > 40 ? `, dan ${names.length - 40} lainnya` : ""}` : ""}
      className={`relative overflow-hidden text-left bg-white border rounded-xl pl-5 pr-4 py-3 shadow-sm transition-colors ${active ? "border-brand-700 ring-2 ring-brand-700/20" : "border-slate-200"} ${onClick ? "hover:border-brand-400" : "cursor-default"}`}>
      <AccentBody icon={icon} label={label} value={value} sub={sub} accent={accent} dim={!value} />
    </Tag>
  );
};

// Kartu nominal halaman periode (user 15 Okt 2026) dengan gaya kartu beraksen desain RUMAT; children = baris tambahan
export const KpiCard = ({ label, value, sub, accent = "brand", icon, testId, children }) => (
  <div className="relative overflow-hidden bg-white border border-slate-200 rounded-xl pl-5 pr-4 py-4 shadow-sm">
    <AccentBody icon={icon} label={label} value={value} sub={sub} accent={accent} big valueTestId={testId} />
    {children}
  </div>
);

// Label kecil berbingkai (mis. "Hanya-lihat · dari ROSY", 15 Okt 2026). Bukan tombol: tanpa efek hover, kursor panah.
// Desain RUMAT: tidak huruf kapital semua, minimal text-xs, warna hanya yang bermakna
const CHIP = {
  slate: "bg-slate-100 text-slate-600 border-slate-200",
  brand: "bg-brand-50 text-brand-700 border-brand-200",
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  rose: "bg-rose-50 text-rose-700 border-rose-200",
};
// large = di samping judul halaman (status periode, user 15 Okt 2026)
export const Chip = ({ tone = "slate", large, testId, title, children }) => (
  <span data-testid={testId} title={title} className={`inline-flex items-center gap-1.5 rounded-md border font-semibold whitespace-nowrap cursor-default ${large ? "px-2.5 py-1 text-sm" : "px-2 py-0.5 text-xs"} ${CHIP[tone] || CHIP.slate}`}>{children}</span>
);

// Status periode sebagai lencana (user 15 Okt 2026: di samping judul halaman periode, dan di samping pilihan Periode di
// Dashboard). Warna mengikuti makna desain RUMAT — draft teal (sedang dikerjakan), menunggu kuning, ditolak merah, terkunci
// hijau; label dari PERIOD_STATUS
const PERIOD_TONE = { draft: "brand", pending_approval: "amber", revision: "rose", approved: "emerald", closed: "slate" };
export const PeriodStatusChip = ({ status, testId }) => (
  <Chip large tone={PERIOD_TONE[status] || "slate"} testId={testId} title="Status periode">
    <span className="h-2 w-2 shrink-0 rounded-full bg-current" aria-hidden="true" />{PERIOD_STATUS[status]?.label || status}
  </Chip>
);

// Tab penyaring berbentuk pil + jumlah (halaman periode & karyawan, 15 Okt 2026). alarm "rose"/"amber" = kelompok yang
// perlu perhatian diberi warna selama ada isinya; tab yang sedang dipakai berwarna brand
const TAB_ALARM = {
  rose: ["border-rose-300 bg-rose-50 text-rose-700 hover:bg-rose-100", "bg-rose-600 text-white"],
  amber: ["border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100", "bg-amber-500 text-white"],
};
export const FilterTab = ({ label, count, on, alarm, testId, ...p }) => {
  const a = !on && count > 0 && TAB_ALARM[alarm];
  return (
    <button type="button" data-testid={testId} aria-pressed={!!on} {...p}
      className={`tap inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors disabled:cursor-default disabled:opacity-50 ${on ? "border-brand-700 bg-brand-700 text-white" : a ? a[0] : "border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:bg-brand-50"}`}>
      {label}
      <span className={`num rounded-full px-1.5 text-xs ${on ? "bg-white/20 text-white" : a ? a[1] : "bg-slate-100 text-slate-600"}`}>{count}</span>
    </button>
  );
};

export const Btn = ({ variant = "primary", className = "", ...p }) => {
  const v = {
    primary: "bg-brand-700 hover:bg-brand-800 text-white",
    outline: "border border-slate-300 bg-white hover:bg-slate-50 hover:border-slate-400 text-slate-800",
    success: "bg-emerald-600 hover:bg-emerald-700 text-white",
    ghost: "hover:bg-slate-100 text-slate-700",
  }[variant];
  return <button {...p} className={`inline-flex items-center gap-1.5 px-4 py-2 min-h-[40px] rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${v} ${className}`} />;
};
