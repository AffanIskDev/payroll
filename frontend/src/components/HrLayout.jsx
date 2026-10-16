import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Building2, LayoutDashboard, Wallet, Users, CalendarClock, Settings2, LogOut, Calculator, BarChart3, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useAuth, isManager, ROLE_LABELS } from "@/context/AuthContext";

// [path, label, icon, end, khusus Manager HRD]
const NAV = [
  ["/hr-manager", "Dashboard", LayoutDashboard, true],
  ["/hr-manager/payroll", "Payroll", Wallet],
  ["/hr-manager/employees", "Karyawan", Users],
  ["/hr-manager/attendance", "Presensi", CalendarClock],
  ["/hr-manager/recap", "Rekap", BarChart3],
  ["/hr-manager/tax", "Pajak", Calculator, false, true],
  ["/hr-manager/config", "Konfigurasi", Settings2, false, true],
];

// Sidebar bisa diciutkan jadi lajur ikon (user 15 Okt 2026: "supaya bisa lebih lebar lihat contentnya"); pilihannya diingat di
// peramban ini. Lebarnya satu variabel CSS --sidebar-w, dipakai juga oleh elemen fixed di halaman (bilah THP review slip).
const CIUT_KEY = "rasa.menu.ciut";
const readCiut = () => {
  try { return localStorage.getItem(CIUT_KEY) === "1"; } catch { return false; }
};

export default function HrLayout() {
  const { user, logout } = useAuth();
  const nav = NAV.filter(([, , , , managerOnly]) => !managerOnly || isManager(user));
  const [ciut, setCiut] = useState(readCiut);
  const toggle = () => setCiut((c) => {
    try { localStorage.setItem(CIUT_KEY, c ? "0" : "1"); } catch { /* tanpa penyimpanan: tetap jalan */ }
    return !c;
  });
  return (
    <div className="min-h-screen bg-background lg:flex" style={{ "--sidebar-w": ciut ? "4.5rem" : "13rem" }}>
      {/* Menu di samping kiri (14 Okt 2026). Satu elemen yang sama berubah bentuk menurut lebar layar, jadi data-testid tidak ganda:
          < lg bar atas berisi ikon, teal medis brand-700 (15 Okt 2026) (nama menu di tooltip; 7 menu Manager muat di layar 360px) · lg ke atas sidebar kiri dengan nama menu,
          nama pengguna & tombol keluar di bagian bawah; diciutkan = ikon saja, nama menu di tooltip. */}
      <aside className="sticky top-0 z-40 bg-brand-700 text-white border-b border-brand-800 lg:border-b-0 lg:h-screen lg:w-[var(--sidebar-w)] lg:shrink-0 lg:transition-[width] lg:duration-200" data-testid="sidebar" data-collapsed={ciut ? "true" : "false"}>
        <div className="h-14 lg:h-full px-4 sm:px-6 lg:px-3 lg:py-5 flex lg:flex-col items-center lg:items-stretch gap-2 sm:gap-3 lg:gap-6">
          <div className={`flex items-center gap-2.5 shrink-0 ${ciut ? "lg:justify-center" : "lg:px-2"}`} title="RASA — RUMAT Administration & Salary Application" data-testid="app-brand">
            {/* [LOGO RUMAT] ganti ikon ini dengan logo resmi bila sudah ada (public/logo-rumat.svg) */}
            <div className="h-8 w-8 lg:h-10 lg:w-10 rounded-lg bg-white text-brand-700 grid place-items-center shrink-0"><Building2 className="h-4 w-4 lg:h-5 lg:w-5" /></div>
            <div className={`hidden sm:block leading-tight ${ciut ? "lg:hidden" : ""}`}>
              <div className="font-extrabold tracking-[0.08em] lg:text-lg">RASA</div>
              <div className="text-xs text-brand-100 hidden lg:block">Aplikasi Penggajian RUMAT</div>
            </div>
          </div>
          <nav id="main-nav" className="flex lg:flex-col items-center lg:items-stretch gap-0.5 sm:gap-1 overflow-x-auto lg:overflow-x-visible lg:overflow-y-auto lg:flex-1" data-testid="main-nav" aria-label="Menu utama">
            {nav.map(([to, label, Icon, end]) => (
              <NavLink key={to} to={to} end={end} title={label} aria-label={label} data-testid={`nav-${label.toLowerCase().replace(/\s/g, "-")}`}
                className={({ isActive }) => `flex items-center gap-3 px-2 sm:px-3 py-3 lg:py-2.5 rounded-lg text-sm whitespace-nowrap transition-colors ${ciut ? "lg:justify-center" : ""} ${isActive ? "bg-white text-brand-700 font-bold shadow-sm" : "text-brand-50 hover:bg-white/15 hover:text-white"}`}>
                <Icon className="h-4 w-4 shrink-0" /> <span className={`hidden ${ciut ? "" : "lg:inline"}`}>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto lg:ml-0 flex flex-col gap-2 lg:border-t lg:border-white/20 lg:pt-3">
            {/* hanya di layar lebar; tablet/HP tetap bar ikon di atas */}
            <button type="button" onClick={toggle} aria-expanded={!ciut} aria-controls="main-nav" data-testid="sidebar-toggle" title={ciut ? "Lebarkan menu" : "Ciutkan menu"}
              className={`hidden lg:flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-brand-100 hover:bg-white/15 hover:text-white transition-colors ${ciut ? "justify-center" : ""}`}>
              {ciut ? <PanelLeftOpen className="h-4 w-4 shrink-0" /> : <><PanelLeftClose className="h-4 w-4 shrink-0" /> Ciutkan menu</>}
            </button>
            <div className={`flex items-center gap-3 ${ciut ? "lg:justify-center" : "lg:px-2"}`}>
              <div className={`min-w-0 lg:flex-1 ${ciut ? "hidden" : "hidden xl:block lg:block"}`}>
                <div className="text-sm font-semibold truncate" data-testid="current-user-name">{user?.name}</div>
                <div className="text-xs text-brand-100 truncate">{ROLE_LABELS[user?.role]}</div>
              </div>
              <button data-testid="logout-button" onClick={logout} aria-label="Keluar" className="p-2.5 sm:p-3 lg:p-2 rounded-lg hover:bg-white/15 shrink-0" title={user?.name ? `Keluar (${user.name} · ${ROLE_LABELS[user?.role] || ""})` : "Keluar"}><LogOut className="h-4 w-4" /></button>
            </div>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        {/* 1600 px (dulu 1400, user 15 Okt 2026): tabel review periode yang penuh angka muat tanpa digeser di layar lebar */}
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
