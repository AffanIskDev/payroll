import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PERIOD_STATUS, periodNameFor, unfinishedSyncDay, formatDate, formatDateRange, localIso, monthRange, firstDayAfter } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import SyncTodayDialog from "@/components/SyncTodayDialog";
import { useAuth, isManager } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const Field = ({ label, testId, ...p }) => (
  <label className="block space-y-1">
    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
    <input data-testid={testId} {...p} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm read-only:bg-slate-50 read-only:text-slate-700" />
  </label>
);

// Periode baru = pilih satu bulan kalender (user 13 Okt 2026): tanggal mulai & selesai mengikuti bulannya, dan Tanggal
// Transfer terisi otomatis tanggal 1 bulan berikutnya (tetap bisa diubah). Bulan yang bisa dipilih: bulan ini dan 12
// bulan sebelumnya, terbaru di atas.
const EMPTY = { month: "", payment_date: "" };
const MONTHS_BACK = 12;
const recentMonths = () => {
  const now = localIso().slice(0, 7);
  let y = Number(now.slice(0, 4)), m = Number(now.slice(5, 7));
  const keys = [];
  for (let i = 0; i <= MONTHS_BACK; i++) {
    keys.push(`${y}-${String(m).padStart(2, "0")}`);
    if (--m === 0) { m = 12; y -= 1; }
  }
  return keys;
};

export default function Periods() {
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(EMPTY);
  const range = f.month ? monthRange(f.month) : null;
  const monthName = range ? periodNameFor(range.start, range.end) : "";
  const [del, setDel] = useState(null);
  const nav = useNavigate();
  const load = () => api.get("/hr/periods").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  // sama dengan aturan backend: satu periode per bulan dan tanggalnya tidak boleh bertumpuk; yang sudah ada tak bisa dipilih
  const months = recentMonths().map((key) => {
    const r = monthRange(key);
    return { key, name: periodNameFor(r.start, r.end), taken: list.some((p) => p.bulan === key || (p.start_date <= r.end && r.start <= p.end_date)) };
  });

  const [syncing, setSyncing] = useState(false);
  const [confirmDay, setConfirmDay] = useState(null);
  // periode yang mencakup hari ini langsung disinkron: tanya dulu, absensi hari ini belum selesai (user 12 Okt 2026)
  const submit = (e) => {
    e.preventDefault();
    if (!range) return;
    const day = unfinishedSyncDay(range.start, range.end);
    if (day) setConfirmDay(day);
    else create();
  };
  const create = async () => {
    setConfirmDay(null);
    setSyncing(true);
    try {
      const { data } = await api.post("/hr/periods", { start_date: range.start, end_date: range.end, payment_date: f.payment_date });
      if (data.sync_error) toast.warning(`Periode ${data.period_name} dibuat, tetapi sinkron gagal: ${data.sync_error}. Buka periodenya lalu ulangi lewat "Fetch Data Terbaru".`, { duration: 10000 });
      else toast.success(`Periode ${data.period_name} dibuat · ${data.employee_count} karyawan disinkron dari ROSY`);
      setOpen(false);
      setF(EMPTY);
      nav(`/hr-manager/payroll/${data.id}`);
    } catch (err) { toast.error(errMsg(err)); } finally { setSyncing(false); }
  };

  const remove = async () => {
    try {
      await api.delete(`/hr/periods/${del.id}`);
      toast.success(`Periode ${del.period_name} dihapus`);
      load();
    } catch (err) { toast.error(errMsg(err)); } finally { setDel(null); }
  };

  return (
    <div>
      <PageTitle title="PAYROLL" subtitle="Siklus penggajian bulanan">
        <Btn data-testid="create-period-button" onClick={() => { setF(EMPTY); setOpen(true); }}><Plus className="h-4 w-4" /> Periode Baru</Btn>
      </PageTitle>
      <Panel>
        {/* HP (user 12 Okt 2026): nama periode jadi tautannya, rentang & tanggal transfer turun ke bawah nama, sehingga
            Status dan tombol hapus tetap terlihat tanpa menggeser tabel */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="periods-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr><th className="text-left px-3 sm:px-5 py-3">Periode</th><th className="hidden sm:table-cell text-left px-5 py-3">Rentang</th><th className="hidden sm:table-cell text-left px-5 py-3">Tgl Bayar</th><th className="text-left px-3 sm:px-5 py-3">Status</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-3 sm:px-5 py-3">
                    <Link to={`/hr-manager/payroll/${p.id}`} className="tap font-semibold text-slate-900 hover:text-brand-700 hover:underline" data-testid={`period-name-${p.id}`}>{p.period_name}</Link>
                    <div className="sm:hidden text-xs text-slate-500">{formatDateRange(p.start_date, p.end_date)}{p.payment_date ? ` · transfer ${formatDate(p.payment_date)}` : ""}</div>
                  </td>
                  <td className="hidden sm:table-cell px-5 py-3 text-slate-600 whitespace-nowrap">{formatDateRange(p.start_date, p.end_date)}</td>
                  <td className="hidden sm:table-cell px-5 py-3 text-slate-600 whitespace-nowrap">{p.payment_date ? formatDate(p.payment_date) : "-"}</td>
                  <td className="px-3 sm:px-5 py-3"><StatusBadge map={PERIOD_STATUS} status={p.status} testId={`period-status-${p.id}`} /></td>
                  <td className="px-3 sm:px-5 py-3 text-right whitespace-nowrap">
                    <Link data-testid={`open-period-${p.id}`} to={`/hr-manager/payroll/${p.id}`} className="tap hidden sm:inline text-brand-700 font-semibold hover:underline">Buka</Link>
                    {(["draft", "revision"].includes(p.status) || (p.status === "pending_approval" && isManager(user))) && (
                      <button data-testid={`delete-period-${p.id}`} onClick={() => setDel(p)} className="tap sm:ml-3 p-1 rounded text-rose-600 hover:bg-rose-50 align-middle" title="Hapus periode"><Trash2 className="h-4 w-4" /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="create-period-dialog">
          <DialogHeader><DialogTitle>Periode Payroll Baru</DialogTitle><DialogDescription>Karyawan, gaji, absensi, lembur, dan Tambahan Bulanan (Transport, Bonus, THR, Potongan Target, Cicilan) langsung disinkron dari ROSY, lalu slip dihitung. Satu bulan hanya satu periode.</DialogDescription></DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <label className="block space-y-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Periode</span>
              <select data-testid="period-month-select" required value={f.month} onChange={(e) => setF({ month: e.target.value, payment_date: e.target.value ? firstDayAfter(e.target.value) : "" })} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
                <option value="">Pilih periode...</option>
                {months.map((m) => <option key={m.key} value={m.key} disabled={m.taken}>{m.name}{m.taken ? " — sudah ada" : ""}</option>)}
              </select>
              {range && <span className="block text-xs text-slate-500" data-testid="period-range-hint">{formatDateRange(range.start, range.end)}</span>}
            </label>
            <Field label="Tanggal Transfer" type="date" testId="period-payment-input" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            <Btn data-testid="period-submit-button" disabled={syncing || !range} className="w-full justify-center">{syncing ? "Menyinkronkan dari ROSY..." : "Simpan & Sinkronisasi"}</Btn>
          </form>
        </DialogContent>
      </Dialog>
      <AlertDialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <AlertDialogContent data-testid="delete-period-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus periode {del?.period_name}?</AlertDialogTitle>
            <AlertDialogDescription>Periode beserta seluruh slip draft-nya akan dihapus permanen. Log absensi tidak terhapus.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-period-cancel">Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="delete-period-confirm" onClick={remove} className="bg-rose-600 hover:bg-rose-700">Hapus</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <SyncTodayDialog day={confirmDay} periodName={monthName} onConfirm={create} onCancel={() => setConfirmDay(null)} />
    </div>
  );
}
