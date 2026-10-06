import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth, isHr } from "@/context/AuthContext";
import Login from "@/pages/Login";
import HrLayout from "@/components/HrLayout";
import Dashboard from "@/pages/hr/Dashboard";
import Periods from "@/pages/hr/Periods";
import PeriodDetail from "@/pages/hr/PeriodDetail";
import Workbench from "@/pages/hr/Workbench";
import Employees from "@/pages/hr/Employees";
import Attendance from "@/pages/hr/Attendance";
import Configs from "@/pages/hr/Configs";
import TaxYtd from "@/pages/hr/TaxYtd";
import TaxForms from "@/pages/hr/TaxForms";
import Schedules from "@/pages/hr/Schedules";
import Rotations from "@/pages/hr/Rotations";
import ShiftRecap from "@/pages/hr/ShiftRecap";
import EmployeeHome from "@/pages/employee/EmployeeHome";
import PayslipDetail from "@/pages/employee/PayslipDetail";

function Guard({ hr, children }) {
  const { user } = useAuth();
  if (user === null) return <div className="p-10 text-sm text-slate-500" data-testid="auth-loading">Memuat...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (hr && !isHr(user)) return <Navigate to="/me" replace />;
  if (!hr && isHr(user)) return <Navigate to="/hr-manager" replace />;
  return children;
}

function Home() {
  const { user } = useAuth();
  if (user === null) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={isHr(user) ? "/hr-manager" : "/me"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/hr-manager" element={<Guard hr><HrLayout /></Guard>}>
            <Route index element={<Dashboard />} />
            <Route path="payroll" element={<Periods />} />
            <Route path="payroll/:pid" element={<PeriodDetail />} />
            <Route path="payroll/:pid/employee/:eid" element={<Workbench />} />
            <Route path="employees" element={<Employees />} />
            <Route path="attendance" element={<Attendance />} />
            <Route path="config" element={<Configs />} />
            <Route path="tax" element={<TaxYtd />} />
            <Route path="tax-forms" element={<TaxForms />} />
            <Route path="schedules" element={<Schedules />} />
            <Route path="rotations" element={<Rotations />} />
            <Route path="shift-recap" element={<ShiftRecap />} />
          </Route>
          <Route path="/me" element={<Guard><EmployeeHome /></Guard>} />
          <Route path="/me/payslip/:sid" element={<Guard><PayslipDetail /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}
