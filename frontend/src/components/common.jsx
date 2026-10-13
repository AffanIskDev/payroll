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
  <section className={`bg-white border border-slate-200 rounded-lg shadow-sm ${className}`}>
    {title && (
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
        <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">{title}</h2>
        {right}
      </div>
    )}
    {children}
  </section>
);

// kartu ringkasan yang sekaligus menyaring tabel (halaman periode, user 10 Okt 2026; halaman karyawan, 12 Okt);
// kursor di atas kartu menampilkan namanya
export const SummaryCard = ({ icon: Icon, label, value, sub, names, warn, active, onClick, testId }) => {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} onClick={onClick} aria-pressed={onClick ? !!active : undefined} data-testid={testId}
      title={names?.length ? `${names.slice(0, 40).join(", ")}${names.length > 40 ? `, dan ${names.length - 40} lainnya` : ""}` : ""}
      className={`text-left bg-white border rounded-lg px-4 py-3 shadow-sm transition-colors ${active ? "border-blue-900 ring-2 ring-blue-900/20" : "border-slate-200"} ${onClick ? "hover:border-blue-400" : "cursor-default"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
        <Icon className={`h-4 w-4 ${active ? "text-blue-900" : "text-slate-400"}`} />
      </div>
      <div className={`num text-2xl font-bold mt-1 ${warn && value ? "text-amber-600" : "text-slate-900"}`}>{value}</div>
      <div className="text-xs text-slate-500 truncate">{sub}</div>
    </Tag>
  );
};

export const Btn = ({ variant = "primary", className = "", ...p }) => {
  const v = {
    primary: "bg-blue-900 hover:bg-slate-900 text-white",
    outline: "border border-slate-300 bg-white hover:bg-slate-50 text-slate-800",
    success: "bg-emerald-600 hover:bg-emerald-700 text-white",
    ghost: "hover:bg-slate-100 text-slate-700",
  }[variant];
  return <button {...p} className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${v} ${className}`} />;
};
