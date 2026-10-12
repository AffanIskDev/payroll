import { NavLink, Outlet } from "react-router-dom";
import { Building2, LayoutDashboard, Wallet, Users, CalendarClock, Settings2, LogOut, Calculator, BarChart3 } from "lucide-react";
import { useAuth, isManager, ROLE_LABELS } from "@/context/AuthContext";

// [path, label, icon, end, khusus Manager HRD]
const NAV = [
  ["/hr-manager", "Dashboard", LayoutDashboard, true],
  ["/hr-manager/payroll", "Payroll", Wallet],
  ["/hr-manager/employees", "Karyawan", Users],
  ["/hr-manager/attendance", "Absensi", CalendarClock],
  ["/hr-manager/recap", "Rekap", BarChart3],
  ["/hr-manager/tax", "Pajak", Calculator, false, true],
  ["/hr-manager/config", "Konfigurasi", Settings2, false, true],
];

export default function HrLayout() {
  const { user, logout } = useAuth();
  const nav = NAV.filter(([, , , , managerOnly]) => !managerOnly || isManager(user));
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 bg-slate-900 text-white border-b border-slate-800">
        {/* Bertahap menurut lebar (12 Okt 2026), supaya menu tidak terpotong & nama tidak terlipat — Manager punya 7 menu:
            < lg ikon saja (nama menu di tooltip; di HP ikon 32px agar 7 menu Manager muat di layar 360px) · lg ikon + teks · xl + nama pengguna · 2xl + kepanjangan RASA */}
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-14 flex items-center gap-2 sm:gap-3 lg:gap-6">
          <div className="flex items-center gap-2 shrink-0" title="RASA — RUMAT Administration & Salary Application" data-testid="app-brand">
            <div className="h-8 w-8 rounded bg-blue-800 grid place-items-center"><Building2 className="h-4 w-4" /></div>
            <div className="hidden sm:block leading-tight">
              <div className="font-bold tracking-tight">RASA</div>
              <div className="text-[11px] text-slate-400 hidden 2xl:block">RUMAT Administration &amp; Salary Application</div>
            </div>
          </div>
          <nav className="flex items-center gap-0.5 sm:gap-1 overflow-x-auto" data-testid="main-nav">
            {nav.map(([to, label, Icon, end]) => (
              <NavLink key={to} to={to} end={end} title={label} aria-label={label} data-testid={`nav-${label.toLowerCase().replace(/\s/g, "-")}`}
                className={({ isActive }) => `flex items-center gap-1.5 px-2 sm:px-3 py-3 lg:py-1.5 rounded text-sm whitespace-nowrap transition-colors ${isActive ? "bg-blue-900 text-white" : "text-slate-300 hover:bg-slate-800"}`}>
                <Icon className="h-4 w-4" /> <span className="hidden lg:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right hidden xl:block">
              <div className="text-sm font-medium whitespace-nowrap" data-testid="current-user-name">{user?.name}</div>
              <div className="text-[11px] text-slate-400 uppercase tracking-wider whitespace-nowrap">{ROLE_LABELS[user?.role]}</div>
            </div>
            <button data-testid="logout-button" onClick={logout} className="p-2.5 sm:p-3 lg:p-2 rounded hover:bg-slate-800" title={user?.name ? `Keluar (${user.name} · ${ROLE_LABELS[user?.role] || ""})` : "Keluar"}><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </header>
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
