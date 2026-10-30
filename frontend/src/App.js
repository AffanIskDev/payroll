import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth, isHr, isManager } from "@/context/AuthContext";
import Login from "@/pages/Login";
import Verify from "@/pages/Verify";
import HrLayout from "@/components/HrLayout";
import Dashboard from "@/pages/hr/Dashboard";
import Periods from "@/pages/hr/Periods";
import PeriodDetail from "@/pages/hr/PeriodDetail";
import SpecialRuns from "@/pages/hr/SpecialRuns";
import SpecialRunDetail from "@/pages/hr/SpecialRunDetail";
import Workbench from "@/pages/hr/Workbench";
import Employees from "@/pages/hr/EmployeesView";
import Attendance from "@/pages/hr/AttendanceView";
import Configs from "@/pages/hr/Configs";
import { TaxPage, RecapPage } from "@/pages/hr/MergedPages";

function Guard({ children }) {
  const { user, logout } = useAuth();
  if (user === null) return <div className="p-10 text-sm text-slate-500" data-testid="auth-loading">Memuat...</div>;
  if (!user) return <Navigate to="/login" replace />;
  // jabatan di ROSY tidak lagi memenuhi syarat: sesi lama berhenti di sini
  if (!isHr(user)) return (
    <div className="min-h-screen grid place-items-center p-6 text-center" data-testid="no-access">
      <div className="space-y-3">
        <div className="text-lg font-semibold">Akun ROSY Anda tidak memiliki akses ke RUSA</div>
        <div className="text-sm text-slate-500">RUSA khusus Manager HRD dan Supervisor HRD sesuai jabatan di ROSY.</div>
        <button onClick={logout} className="text-sm font-semibold text-brand-700 underline">Keluar</button>
      </div>
    </div>
  );
  return children;
}

// Pajak & Konfigurasi: khusus Manager HRD
function ManagerOnly({ children }) {
  const { user } = useAuth();
  return isManager(user) ? children : <Navigate to="/hr-manager" replace />;
}

function Home() {
  const { user } = useAuth();
  if (user === null) return null;
  return <Navigate to={user ? "/hr-manager" : "/login"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          {/* publik, tanpa login: dibuka dari QR di slip gaji (user 14 Okt 2026) */}
          <Route path="/verifikasi/:code" element={<Verify />} />
          <Route path="/hr-manager" element={<Guard><HrLayout /></Guard>}>
            <Route index element={<Dashboard />} />
            <Route path="payroll" element={<Periods />} />
            {/* THR & Bonus Tahunan (30 Okt 2026): rute tetap menang atas payroll/:pid */}
            <Route path="payroll/thr" element={<SpecialRuns runType="thr" />} />
            <Route path="payroll/thr/:pid" element={<SpecialRunDetail runType="thr" />} />
            <Route path="payroll/bonus-tahunan" element={<SpecialRuns runType="bonus_tahunan" />} />
            <Route path="payroll/bonus-tahunan/:pid" element={<SpecialRunDetail runType="bonus_tahunan" />} />
            <Route path="payroll/:pid" element={<PeriodDetail />} />
            <Route path="payroll/:pid/employee/:eid" element={<Workbench />} />
            <Route path="employees" element={<Employees />} />
            <Route path="attendance" element={<Attendance />} />
            <Route path="config" element={<ManagerOnly><Configs /></ManagerOnly>} />
            <Route path="tax" element={<ManagerOnly><TaxPage /></ManagerOnly>} />
            <Route path="tax-forms" element={<Navigate to="/hr-manager/tax?tab=a1" replace />} />
            <Route path="recap" element={<RecapPage />} />
            <Route path="shift-recap" element={<Navigate to="/hr-manager/recap?tab=shift" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}
