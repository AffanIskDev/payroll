import { NavLink } from "react-router-dom";
import { Users, FileSpreadsheet } from "lucide-react";
import { useAuth, isManager } from "@/context/AuthContext";

// Dua halaman di bawah menu Karyawan (user 3 Nov 2026): daftar & import gaji. Import hanya untuk Manager HRD (data gaji).
const TABS = [
  ["/hr-manager/employees", "Daftar Karyawan", Users, true, false],
  ["/hr-manager/employees/import", "Import Karyawan & Gaji", FileSpreadsheet, false, true],
];

export default function EmployeeTabs() {
  const { user } = useAuth();
  const tabs = TABS.filter(([, , , , managerOnly]) => !managerOnly || isManager(user));
  if (tabs.length < 2) return null;
  return (
    <div className="mb-4 flex gap-1 border-b border-slate-200" data-testid="employee-subnav" role="tablist">
      {tabs.map(([to, label, Icon, end]) => (
        <NavLink key={to} to={to} end={end} role="tab" data-testid={`employee-tab-link-${to.split("/").pop()}`}
          className={({ isActive }) => `-mb-px inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${isActive ? "border-brand-700 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"}`}>
          <Icon className="h-4 w-4" /> {label}
        </NavLink>
      ))}
    </div>
  );
}
