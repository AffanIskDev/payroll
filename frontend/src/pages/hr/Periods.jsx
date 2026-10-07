import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PERIOD_STATUS } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const Field = ({ label, testId, ...p }) => (
  <label className="block space-y-1">
    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
    <input data-testid={testId} {...p} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
  </label>
);

export default function Periods() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ period_name: "", start_date: "", end_date: "", payment_date: "" });
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
      toast.success(`Periode dibuat · ${data.employee_count} karyawan diambil dari ROSY`);
      setOpen(false);
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
                  {["draft", "pending_approval"].includes(p.status) && (
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
          <DialogHeader><DialogTitle>Periode Payroll Baru</DialogTitle><DialogDescription>Data karyawan & gaji akan diambil otomatis dari ROSY.</DialogDescription></DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <Field label="Nama Periode" testId="period-name-input" required placeholder="April 2026" value={f.period_name} onChange={(e) => setF({ ...f, period_name: e.target.value })} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Mulai" type="date" testId="period-start-input" required value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
              <Field label="Selesai" type="date" testId="period-end-input" required value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} />
            </div>
            <Field label="Tanggal Transfer" type="date" testId="period-payment-input" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            <Btn data-testid="period-submit-button" disabled={syncing} className="w-full justify-center">{syncing ? "Mengambil data karyawan dari ROSY..." : "Simpan & Ambil Data Karyawan (ROSY)"}</Btn>
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
