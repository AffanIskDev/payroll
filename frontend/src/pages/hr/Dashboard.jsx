import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users, UserPlus, UserMinus, UserX, AlertTriangle, Wallet, Receipt, HeartPulse, HardHat, ArrowRight, BellRing, XCircle, RefreshCw, ChevronDown, LockKeyhole } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { rp, PERIOD_STATUS, DATA_ISSUE_LABELS, formatDate, formatDateRange, localIso, unfinishedSyncDay } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import SyncTodayDialog from "@/components/SyncTodayDialog";

const Stat = ({ icon: Icon, label, value, hint, tone = "text-slate-900", compact, testId }) => (
  <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm fade-up">
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      <Icon className="h-4 w-4 text-slate-400" />
    </div>
    <div data-testid={testId} className={`num font-bold mt-3 ${compact ? "text-xl whitespace-nowrap" : "text-2xl"} ${tone}`}>{value}</div>
    {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
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

// Kelompok "Perlu Ditinjau" (user 10 Okt 2026): siapa yang keluar/masuk, tidak digaji, digaji tidak penuh, absensi & data
const GROUP_INFO = {
  left: ["Keluar di periode ini, atau ada di periode sebelumnya tapi tidak dikirim ROSY lagi", "text-rose-700"],
  new: ["Mulai bekerja di periode ini — cek Kontrak Gaji & slip pertamanya", "text-blue-900"],
  skipped: ["Ada di ROSY tapi tidak masuk periode ini, jadi tidak digaji", "text-amber-700"],
  partial: ["Prorata: masuk, keluar, atau cuti melahirkan di tengah periode; sakit berkepanjangan; cuti di luar tanggungan", "text-amber-700"],
  attendance: ["Alfa/izin (ikut memotong gaji pokok), tanpa data absensi, atau belum tertaut RUMATKU", "text-amber-700"],
  data: ["Data karyawan di ROSY yang belum lengkap — tidak menghalangi payroll", "text-slate-600"],
};

const ReviewGroup = ({ g, pid, open, onToggle }) => {
  const [info, tone] = GROUP_INFO[g.key] || ["", "text-slate-700"];
  return (
    <div className="border-b border-slate-100 last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open} data-testid={`review-group-${g.key}`} className="w-full flex items-center justify-between gap-4 px-5 py-3 text-left hover:bg-slate-50">
        <span>
          <span className="block text-sm font-semibold text-slate-800">{g.title}</span>
          <span className="block text-xs text-slate-500">{info}</span>
        </span>
        <span className="flex items-center gap-2">
          <span className={`num text-lg font-bold ${g.items.length ? tone : "text-slate-300"}`} data-testid={`review-count-${g.key}`}>{g.items.length}</span>
          <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </button>
      {open && (
        <div className="pb-2 max-h-80 overflow-y-auto">
          {g.items.map((it, i) => (
            <div key={`${it.employee_id || it.name}-${i}`} className="flex items-start justify-between gap-4 px-5 py-1.5 text-sm hover:bg-slate-50">
              <div>
                <span className="font-medium text-slate-800">{it.name}</span> <span className="num text-xs text-slate-400">{it.nik}</span>
                <div className="text-xs text-slate-500">{g.key === "data" ? (it.issues || []).map((x) => DATA_ISSUE_LABELS[x] || x).join(", ") : it.note}</div>
              </div>
              {it.has_slip && <Link to={`/hr-manager/payroll/${pid}/employee/${it.employee_id}`} className="text-xs font-semibold text-blue-900 hover:underline whitespace-nowrap">Review</Link>}
            </div>
          ))}
          {!g.items.length && <div className="px-5 py-1.5 text-xs text-slate-400">Tidak ada.</div>}
        </div>
      )}
    </div>
  );
};

export default function Dashboard() {
  const { user } = useAuth();
  const [notes, setNotes] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [d, setD] = useState(null);
  const [open, setOpen] = useState({});
  const [syncing, setSyncing] = useState(false);
  const [confirmDay, setConfirmDay] = useState(null);

  const load = useCallback((pid) => api.get("/hr/dashboard/employees", { params: pid ? { pid } : {} }).then((r) => setD(r.data)), []);
  const loadLists = useCallback(() => {
    api.get("/hr/periods").then((r) => setPeriods(r.data));
    api.get("/hr/notifications").then((r) => setNotes(r.data));
  }, []);
  useEffect(() => { load(); loadLists(); }, [load, loadLists]);

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, counts, groups, payroll } = d;
  const editable = period && ["draft", "revision"].includes(period.status);

  // Pindahan tombol "Sinkron dari ROSY" dari halaman periode (user 10 Okt 2026): satu tombol mengambil karyawan & gaji,
  // absensi, klaim lembur, dan Tambahan Bulanan ROSY untuk periode yang dipilih, lalu menghitung ulang slip
  const sync = async () => {
    setConfirmDay(null);
    setSyncing(true);
    try {
      await api.post(`/hr/periods/${period.id}/fetch-attendance`);
      toast.success(`Sinkron ${period.period_name} dari ROSY selesai & payroll dihitung ulang`);
    } catch (e) { toast.error(errMsg(e)); } finally {
      setSyncing(false);
      await load(period.id);
      loadLists();
    }
  };
  // periode yang masih berjalan: tanya dulu, karena absensi hari ini belum selesai (user 12 Okt 2026)
  const requestSync = () => {
    const day = unfinishedSyncDay(period.start_date, period.end_date);
    if (day) setConfirmDay(day);
    else sync();
  };
  const lastSyncDay = period?.last_sync_at ? localIso(new Date(period.last_sync_at)) : null;
  const syncedMidPeriod = editable && lastSyncDay && period.start_date <= lastSyncDay && lastSyncDay <= period.end_date;

  return (
    <div data-testid="hr-dashboard">
      <PageTitle title="Dashboard Payroll" subtitle={period ? <><span className="block">{formatDateRange(period.start_date, period.end_date)}</span><span className="block" data-testid="dashboard-sync-status">Sinkron terakhir: {period.last_sync_at ? new Date(period.last_sync_at).toLocaleString("id-ID") : "belum pernah"}{syncedMidPeriod && <span className="text-amber-700" data-testid="dashboard-sync-midperiod"> · diambil saat periode berjalan, alfa {formatDate(lastSyncDay)} belum final</span>}</span></> : "Belum ada periode — buat di menu Payroll"}>
        {period && <StatusBadge map={PERIOD_STATUS} status={period.status} testId="dashboard-period-status" />}
        {periods.length > 0 && (
          <select data-testid="dashboard-period-select" value={period?.id || ""} onChange={(e) => load(e.target.value)} className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
            {periods.map((p) => <option key={p.id} value={p.id}>{p.period_name}</option>)}
          </select>
        )}
        {period && <Btn variant="primary" data-testid="dashboard-sync-button" disabled={syncing || !editable} onClick={requestSync} title={editable ? "Karyawan & gaji, absensi, klaim lembur, dan Tambahan Bulanan (Transport, Bonus, THR, Potongan Target, Cicilan) terbaru dari ROSY" : "Periode ini sudah diajukan atau dikunci, jadi tidak bisa disinkron lagi"}><RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} /> {syncing ? "Menyinkronkan..." : "Sinkron dari ROSY"}</Btn>}
      </PageTitle>
      {period?.last_sync_error && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3 text-sm" data-testid="dashboard-sync-error">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>Sinkron dari ROSY terakhir gagal: {period.last_sync_error}. Klik "Sinkron dari ROSY" untuk mencoba lagi.</span>
        </div>
      )}
      <div className="mb-6 space-y-2" data-testid="notifications-panel">
        {notes.map((n) => <Notice key={n.period_id} n={n} />)}
        {!notes.length && <div className="text-xs text-slate-400" data-testid="no-notifications">{user?.role === "manager_hrd" ? "Tidak ada draft payroll yang menunggu approval." : "Tidak ada draft payroll yang ditolak."}</div>}
      </div>
      {period && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
            <Stat icon={Users} label="Karyawan Periode Ini" value={counts.in_period} hint="ikut digaji (punya Kontrak Gaji)" testId="stat-employees" />
            <Stat icon={UserPlus} label="Karyawan Baru" value={counts.new} tone={counts.new ? "text-blue-900" : "text-slate-900"} hint="mulai bekerja di periode ini" testId="stat-new" />
            <Stat icon={UserMinus} label="Karyawan Keluar" value={counts.left} tone={counts.left ? "text-rose-600" : "text-slate-900"} hint="keluar / tidak dikirim ROSY lagi" testId="stat-left" />
            <Stat icon={UserX} label="Tidak Ikut Digaji" value={counts.skipped} tone={counts.skipped ? "text-amber-600" : "text-slate-900"} hint="mis. belum punya Kontrak Gaji" testId="stat-skipped" />
            <Stat icon={AlertTriangle} label="Perlu Ditinjau" value={counts.review} tone={counts.review ? "text-amber-600" : "text-emerald-600"} hint="karyawan di daftar bawah" testId="stat-review" />
          </div>
          <Panel title={`Perlu Ditinjau · ${period.period_name}`} className="mb-6">
            {groups.map((g) => (
              <ReviewGroup key={g.key} g={g} pid={period.id} open={!!open[g.key]} onToggle={() => setOpen({ ...open, [g.key]: !open[g.key] })} />
            ))}
          </Panel>
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
            <Stat icon={Wallet} label="Total Diterima" compact value={rp(payroll.total_thp)} tone="text-emerald-600" testId="stat-total-thp" />
            <Stat icon={Receipt} label="Total PPh 21" compact value={rp(payroll.total_pph21)} testId="stat-total-pph21" />
            <Stat icon={HeartPulse} label="Setoran BPJS Kesehatan" compact value={rp(payroll.total_bpjs_kes)} testId="stat-total-bpjs-kes" />
            <Stat icon={HardHat} label="Setoran BPJS TK" compact value={rp(payroll.total_bpjs_tk)} testId="stat-total-bpjs-tk" />
            <Stat icon={LockKeyhole} label="Slip Dikunci" value={`${payroll.approved}/${payroll.slips}`} tone={payroll.slips && payroll.approved === payroll.slips ? "text-emerald-600" : "text-amber-600"} testId="stat-approved" />
          </div>
        </>
      )}
      <Panel title="Periode Penggajian" right={<Link to="/hr-manager/payroll" className="text-xs font-semibold text-blue-900 hover:underline" data-testid="dashboard-all-periods-link">Kelola</Link>}>
        <div className="divide-y divide-slate-100">
          {periods.map((p) => (
            <Link key={p.id} to={`/hr-manager/payroll/${p.id}`} data-testid={`dashboard-period-${p.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 group">
              <div>
                <div className="font-semibold text-slate-800">{p.period_name}</div>
                <div className="text-xs text-slate-500">{formatDateRange(p.start_date, p.end_date)}</div>
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
      <SyncTodayDialog day={confirmDay} periodName={period?.period_name} onConfirm={sync} onCancel={() => setConfirmDay(null)} />
    </div>
  );
}
