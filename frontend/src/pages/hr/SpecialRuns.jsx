import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, formatDate, localIso } from "@/lib/format";
import { RUNS, runPath } from "@/lib/runs";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import { PERIOD_STATUS } from "@/lib/format";
import { useAuth, isManager } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

// Daftar run THR / Bonus Tahunan (user 30 Okt 2026). Satu run = satu pembayaran dengan tanggal bayarnya sendiri; masa pajaknya
// bulan tanggal bayar itu, bukan tahun THR / bonus itu diperoleh.
export default function SpecialRuns({ runType }) {
  const run = RUNS[runType];
  const { user } = useAuth();
  const nav = useNavigate();
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", pay_date: "" });
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState(null);
  const load = () => api.get("/hr/special-runs", { params: { run_type: runType } }).then((r) => setList(r.data));
  useEffect(() => { setList(null); load(); }, [runType]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/hr/special-runs", { run_type: runType, title: f.title, pay_date: f.pay_date });
      if (data.sync_error) toast.warning(`Run ${data.period_name} dibuat, tetapi sinkron gagal: ${data.sync_error}. Buka run-nya lalu ulangi lewat "Tarik dari ROSY".`, { duration: 10000 });
      else toast.success(`Run ${data.period_name} dibuat · ${data.employee_count} karyawan disinkron dari ROSY`);
      setOpen(false);
      setF({ title: "", pay_date: "" });
      nav(runPath(runType, data.id));
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  const remove = async () => {
    try {
      await api.delete(`/hr/periods/${del.id}`);
      toast.success(`Run ${del.period_name} dihapus`);
      load();
    } catch (err) { toast.error(errMsg(err)); } finally { setDel(null); }
  };

  return (
    <div data-testid={`special-runs-${runType}`}>
      <PageTitle title={`PAYROLL ${run.label.toUpperCase()}`} subtitle={runType === "thr" ? "THR dibayar terpisah dari gaji bulanan" : "Bonus tahunan dibayar terpisah dari gaji bulanan"}>
        <Btn data-testid="create-run-button" onClick={() => { setF({ title: "", pay_date: localIso() }); setOpen(true); }}><Plus className="h-4 w-4" /> Run {run.label} Baru</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="runs-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="text-left px-3 sm:px-5 py-3">Run</th>
                <th className="text-left px-3 sm:px-5 py-3">Tgl Bayar</th>
                <th className="hidden md:table-cell text-right px-5 py-3">Penerima</th>
                <th className="hidden md:table-cell text-right px-5 py-3">Total {run.label}</th>
                <th className="hidden md:table-cell text-right px-5 py-3">PPh 21</th>
                <th className="text-right px-3 sm:px-5 py-3">Total Diterima</th>
                <th className="text-left px-3 sm:px-5 py-3">Status</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(list || []).map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-3 sm:px-5 py-3"><Link to={runPath(runType, p.id)} className="tap font-semibold text-slate-900 hover:text-brand-700 hover:underline" data-testid={`run-name-${p.id}`}>{p.period_name}</Link></td>
                  <td className="px-3 sm:px-5 py-3 text-slate-600 whitespace-nowrap">{formatDate(p.payment_date)}</td>
                  <td className="hidden md:table-cell px-5 py-3 text-right num">{p.summary.slips}</td>
                  <td className="hidden md:table-cell px-5 py-3 text-right num">{rp(p.summary.nominal)}</td>
                  <td className="hidden md:table-cell px-5 py-3 text-right num text-slate-700">{rp(p.summary.pph21)}</td>
                  <td className="px-3 sm:px-5 py-3 text-right num font-semibold">{rp(p.summary.thp)}</td>
                  <td className="px-3 sm:px-5 py-3"><StatusBadge map={PERIOD_STATUS} status={p.status} testId={`run-status-${p.id}`} /></td>
                  <td className="px-3 sm:px-5 py-3 text-right whitespace-nowrap">
                    <Link to={runPath(runType, p.id)} className="tap hidden sm:inline text-brand-700 font-semibold hover:underline">Buka</Link>
                    {(["draft", "revision"].includes(p.status) || (p.status === "pending_approval" && isManager(user))) && (
                      <button data-testid={`delete-run-${p.id}`} onClick={() => setDel(p)} className="tap sm:ml-3 p-1 rounded text-rose-600 hover:bg-rose-50 align-middle" title="Hapus run"><Trash2 className="h-4 w-4" /></button>
                    )}
                  </td>
                </tr>
              ))}
              {list && !list.length && <tr><td colSpan={8} className="px-5 py-10 text-center text-slate-500" data-testid="runs-empty">Belum ada run {run.label}. Klik “Run {run.label} Baru”.</td></tr>}
              {!list && <tr><td colSpan={8} className="px-5 py-10 text-center text-slate-500">Memuat...</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="create-run-dialog">
          <DialogHeader>
            <DialogTitle>Run {run.label} Baru</DialogTitle>
            <DialogDescription>Karyawan dan nominal {run.label} dari ROSY ditarik langsung; nominal bisa diisi atau diubah di RUSA setelahnya. PPh 21 dihitung bersama gaji bulan tanggal bayar.</DialogDescription>
          </DialogHeader>
          <form onSubmit={create} className="space-y-3">
            <label className="block space-y-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Nama (opsional)</span>
              <input data-testid="run-title-input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={`mis. ${run.titleHint}`} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Tanggal Bayar</span>
              <input data-testid="run-paydate-input" type="date" required value={f.pay_date} onChange={(e) => setF({ ...f, pay_date: e.target.value })} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
              <span className="block text-xs text-slate-500">Menentukan masa pajak: dibayar Januari 2027 = penghasilan 2027, dihitung di rekonsiliasi Desember 2027.</span>
            </label>
            <Btn data-testid="run-submit-button" disabled={busy || !f.pay_date} className="w-full justify-center">{busy ? "Menyinkronkan dari ROSY..." : "Simpan & Tarik dari ROSY"}</Btn>
          </form>
        </DialogContent>
      </Dialog>
      <AlertDialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <AlertDialogContent data-testid="delete-run-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus run {del?.period_name}?</AlertDialogTitle>
            <AlertDialogDescription>Run beserta slip draft dan nominal yang diisi di RUSA akan dihapus permanen.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="delete-run-confirm" onClick={remove} className="bg-rose-600 hover:bg-rose-700">Hapus</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
