import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PERIOD_STATUS, periodNameFor } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import { useAuth, isManager } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const Field = ({ label, testId, ...p }) => (
  <label className="block space-y-1">
    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
    <input data-testid={testId} {...p} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm read-only:bg-slate-50 read-only:text-slate-700" />
  </label>
);

const EMPTY = { period_name: "", start_date: "", end_date: "", payment_date: "" };

export default function Periods() {
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(EMPTY);
  const autoName = periodNameFor(f.start_date, f.end_date);
  const [del, setDel] = useState(null);
  const nav = useNavigate();
  const load = () => api.get("/hr/periods").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const [syncing, setSyncing] = useState(false);
  const create = async (e) => {
    e.preventDefault();
    setSyncing(true);
    try {
      const { data } = await api.post("/hr/periods", f);
      if (data.sync_error) toast.warning(`Periode ${data.period_name} dibuat, tetapi sinkron gagal: ${data.sync_error}. Klik "Sinkron dari ROSY" untuk mencoba lagi.`, { duration: 10000 });
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
      <PageTitle title="Periode Payroll" subtitle="Siklus penggajian bulanan">
        <Btn data-testid="create-period-button" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Periode Baru</Btn>
      </PageTitle>
      <Panel>
        <table className="w-full text-sm" data-testid="periods-table">
          <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="text-left px-5 py-3">Periode</th><th className="text-left px-5 py-3">Rentang</th><th className="text-left px-5 py-3">Tgl Bayar</th><th className="text-left px-5 py-3">Status</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {list.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50">
                <td className="px-5 py-3 font-semibold">{p.period_name}</td>
                <td className="px-5 py-3 num text-slate-600">{p.start_date} → {p.end_date}</td>
                <td className="px-5 py-3 num text-slate-600">{p.payment_date || "-"}</td>
                <td className="px-5 py-3"><StatusBadge map={PERIOD_STATUS} status={p.status} testId={`period-status-${p.id}`} /></td>
                <td className="px-5 py-3 text-right whitespace-nowrap">
                  <Link data-testid={`open-period-${p.id}`} to={`/hr-manager/payroll/${p.id}`} className="text-blue-900 font-semibold hover:underline">Buka</Link>
                  {(["draft", "revision"].includes(p.status) || (p.status === "pending_approval" && isManager(user))) && (
                    <button data-testid={`delete-period-${p.id}`} onClick={() => setDel(p)} className="ml-3 p-1 rounded text-rose-600 hover:bg-rose-50 align-middle" title="Hapus periode"><Trash2 className="h-4 w-4" /></button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="create-period-dialog">
          <DialogHeader><DialogTitle>Periode Payroll Baru</DialogTitle><DialogDescription>Karyawan, gaji, absensi, lembur, dan Transport Homecare langsung disinkron dari ROSY, lalu slip dihitung. Satu bulan hanya satu periode.</DialogDescription></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Mulai" type="date" testId="period-start-input" required value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
              <Field label="Selesai" type="date" testId="period-end-input" required value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} />
            </div>
            {autoName || !f.start_date || !f.end_date
              ? <Field label="Nama Periode (otomatis)" testId="period-name-input" readOnly value={autoName || ""} placeholder="Terisi otomatis dari tanggal" />
              : <Field label="Nama Periode (lintas bulan)" testId="period-name-input" required placeholder="mis. Payroll 26 Sep – 25 Okt 2026" value={f.period_name} onChange={(e) => setF({ ...f, period_name: e.target.value })} />}
            <Field label="Tanggal Transfer" type="date" testId="period-payment-input" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            <Btn data-testid="period-submit-button" disabled={syncing} className="w-full justify-center">{syncing ? "Menyinkronkan dari ROSY..." : "Simpan & Sinkron dari ROSY"}</Btn>
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
    </div>
  );
}
