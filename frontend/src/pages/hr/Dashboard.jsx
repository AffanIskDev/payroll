import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users, Wallet, Clock, Receipt, ArrowRight, HeartPulse, HardHat, BellRing, XCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { rp, PERIOD_STATUS } from "@/lib/format";
import { PageTitle, Panel, StatusBadge } from "@/components/common";

const Stat = ({ icon: Icon, label, value, tone = "text-slate-900", testId }) => (
  <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm fade-up">
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      <Icon className="h-4 w-4 text-slate-400" />
    </div>
    <div data-testid={testId} className={`num text-2xl font-bold mt-3 ${tone}`}>{value}</div>
  </div>
);

const Notice = ({ n }) => {
  const rejected = n.kind === "rejected";
  return (
    <Link to={`/hr-manager/payroll/${n.period_id}`} data-testid={`notification-${n.period_id}`} className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors fade-up ${rejected ? "bg-rose-50 border-rose-200 hover:bg-rose-100" : "bg-amber-50 border-amber-200 hover:bg-amber-100"}`}>
      {rejected ? <XCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" /> : <BellRing className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />}
      <div className="text-sm flex-1">
        <div className={`font-semibold ${rejected ? "text-rose-800" : "text-amber-900"}`}>{rejected ? `Draft ${n.period_name} ditolak — perlu dikoreksi` : `Draft ${n.period_name} diajukan — menunggu approval Anda`}</div>
        <div className="text-xs text-slate-600 mt-0.5">oleh {n.by} · <span className="num">{n.at ? new Date(n.at).toLocaleString("id-ID") : "-"}</span></div>
        {n.reason && <div className="text-xs text-rose-700 mt-1">Alasan: {n.reason}</div>}
      </div>
      <ArrowRight className="h-4 w-4 text-slate-400 mt-1" />
    </Link>
  );
};

export default function Dashboard() {
  const [notes, setNotes] = useState([]);
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [periods, setPeriods] = useState([]);
  useEffect(() => {
    api.get("/hr/dashboard").then((r) => setD(r.data));
    api.get("/hr/periods").then((r) => setPeriods(r.data));
    api.get("/hr/notifications").then((r) => setNotes(r.data));
  }, []);
  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const lp = d.latest_period;
  return (
    <div data-testid="hr-dashboard">
      <PageTitle title="Dashboard Payroll" subtitle={lp ? `Periode terbaru: ${lp.period_name}` : "Belum ada periode"} />
      <div className="mb-6 space-y-2" data-testid="notifications-panel">
        {notes.map((n) => <Notice key={n.period_id} n={n} />)}
        {!notes.length && <div className="text-xs text-slate-400" data-testid="no-notifications">{user?.role === "manager_hrd" ? "Tidak ada draft payroll yang menunggu approval." : "Tidak ada draft payroll yang ditolak."}</div>}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 mb-6">
        <Stat icon={Users} label="Karyawan" value={d.employees} testId="stat-employees" />
        <Stat icon={Wallet} label="Total Diterima" value={rp(d.total_thp)} tone="text-emerald-600" testId="stat-total-thp" />
        <Stat icon={Receipt} label="Total PPh 21" value={rp(d.total_pph21)} testId="stat-total-pph21" />
        <Stat icon={Clock} label="Menunggu Review" value={`${d.pending ?? 0} slip`} tone="text-amber-600" testId="stat-pending" />
        <Stat icon={HeartPulse} label="Setoran BPJS Kesehatan" value={rp(d.total_bpjs_kes)} testId="stat-total-bpjs-kes" />
        <Stat icon={HardHat} label="Setoran BPJS TK" value={rp(d.total_bpjs_tk)} testId="stat-total-bpjs-tk" />
      </div>
      <Panel title="Periode Penggajian" right={<Link to="/hr-manager/payroll" className="text-xs font-semibold text-blue-900 hover:underline" data-testid="dashboard-all-periods-link">Kelola</Link>}>
        <div className="divide-y divide-slate-100">
          {periods.map((p) => (
            <Link key={p.id} to={`/hr-manager/payroll/${p.id}`} data-testid={`dashboard-period-${p.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 group">
              <div>
                <div className="font-semibold text-slate-800">{p.period_name}</div>
                <div className="text-xs text-slate-500 num">{p.start_date} → {p.end_date}</div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge map={PERIOD_STATUS} status={p.status} />
                <ArrowRight className="h-4 w-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
              </div>
            </Link>
          ))}
          {!periods.length && <div className="px-5 py-6 text-sm text-slate-500">Belum ada periode.</div>}
        </div>
      </Panel>
    </div>
  );
}
