import { NavLink, Outlet } from "react-router-dom";
import { Building2, LayoutDashboard, Wallet, Users, CalendarClock, Settings2, LogOut, Calculator, CalendarRange, BarChart3 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  ["/hr-manager", "Dashboard", LayoutDashboard, true],
  ["/hr-manager/payroll", "Payroll", Wallet],
  ["/hr-manager/employees", "Karyawan", Users],
  ["/hr-manager/attendance", "Absensi", CalendarClock],
  ["/hr-manager/schedules", "Jadwal-Shift", CalendarRange],
  ["/hr-manager/shift-recap", "Rekap Shift", BarChart3],
  ["/hr-manager/tax", "Pajak", Calculator],
  ["/hr-manager/config", "Konfigurasi", Settings2],
];

export default function HrLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 bg-slate-900 text-white border-b border-slate-800">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-14 flex items-center gap-6">
          <div className="flex items-center gap-2 shrink-0">
            <div className="h-8 w-8 rounded bg-blue-800 grid place-items-center"><Building2 className="h-4 w-4" /></div>
            <span className="font-bold tracking-tight hidden sm:inline">ROSY Payroll</span>
          </div>
          <nav className="flex items-center gap-1 overflow-x-auto">
            {NAV.map(([to, label, Icon, end]) => (
              <NavLink key={to} to={to} end={end} data-testid={`nav-${label.toLowerCase().replace(/\s/g, "-")}`}
                className={({ isActive }) => `flex items-center gap-1.5 px-3 py-1.5 rounded text-sm whitespace-nowrap transition-colors ${isActive ? "bg-blue-900 text-white" : "text-slate-300 hover:bg-slate-800"}`}>
                <Icon className="h-4 w-4" /> <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium" data-testid="current-user-name">{user?.name}</div>
              <div className="text-[11px] text-slate-400 uppercase tracking-wider">{user?.role === "manager_hrd" ? "Manager HRD" : "Staff HR / Admin Payroll"}</div>
            </div>
            <button data-testid="logout-button" onClick={logout} className="p-2 rounded hover:bg-slate-800" title="Keluar"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </header>
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
