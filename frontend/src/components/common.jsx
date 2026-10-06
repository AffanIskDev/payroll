export const StatusBadge = ({ map, status, testId }) => {
  const s = map[status] || { label: status, cls: "bg-slate-100 text-slate-600 border-slate-300" };
  return (
    <span data-testid={testId} className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-semibold uppercase tracking-wide ${s.cls}`}>
      {s.label}
    </span>
  );
};

export const PageTitle = ({ title, subtitle, children }) => (
  <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-6">
    <div>
      <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
      {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);

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

export const Btn = ({ variant = "primary", className = "", ...p }) => {
  const v = {
    primary: "bg-blue-900 hover:bg-slate-900 text-white",
    outline: "border border-slate-300 bg-white hover:bg-slate-50 text-slate-800",
    success: "bg-emerald-600 hover:bg-emerald-700 text-white",
    ghost: "hover:bg-slate-100 text-slate-700",
  }[variant];
  return <button {...p} className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${v} ${className}`} />;
};
