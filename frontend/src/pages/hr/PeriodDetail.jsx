import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Play, LockKeyhole, ChevronLeft, Landmark, Send, XCircle, AlertTriangle, History } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp, PERIOD_STATUS, SLIP_STATUS, PAYROLL_STATUS_LABELS } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const ACTIONS = { submitted: "Diajukan ke Manager", rejected: "Ditolak", approved: "Approve & Lock" };

export default function PeriodDetail() {
  const { pid } = useParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { user } = useAuth();
  const isManager = user?.role === "manager_hrd";
  const load = useCallback(() => api.get(`/hr/periods/${pid}`).then((r) => setD(r.data)), [pid]);
  useEffect(() => { load(); }, [load]);

  const act = async (path, msg, body) => {
    setBusy(true);
    try {
      await api.post(`/hr/periods/${pid}/${path}`, body);
      toast.success(msg);
      await load();
      return true;
    } catch (e) { toast.error(errMsg(e)); return false; } finally { setBusy(false); }
  };
  const reject = async () => {
    if (await act("reject", "Draft dikembalikan ke Staff HR untuk dikoreksi", { reason })) {
      setRejectOpen(false);
      setReason("");
    }
  };

  const exportBsi = async () => {
    try {
      const h = await saveFile("post", `/hr/periods/${pid}/export-bsi`, "BSI_Payroll.csv");
      const skipped = h["x-skipped-niks"];
      toast.success(`CSV BSI diunduh: ${h["x-exported-count"]} transfer${skipped ? ` · dilewati (THP 0 / tanpa rekening): ${skipped}` : ""}`);
    } catch (e) { toast.error(await blobErrMsg(e)); }
  };

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, payslips } = d;
  const editable = ["draft", "revision"].includes(period.status);
  const pending = period.status === "pending_approval";
  const approvedCount = payslips.filter((s) => s.status === "approved").length;
  const sum = (k) => payslips.reduce((a, s) => a + (s[k] || 0), 0);

  return (
    <div data-testid="period-detail-page">
      <Link to="/hr-manager/payroll" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua periode</Link>
      <PageTitle title={period.period_name} subtitle={`${period.start_date} → ${period.end_date} · Transfer ${period.payment_date || "-"}`}>
        <StatusBadge map={PERIOD_STATUS} status={period.status} testId="period-status-badge" />
        <Btn variant="outline" data-testid="process-payroll-button" disabled={busy || !editable} onClick={() => act("process", "Batch payroll selesai dihitung")}><Play className="h-4 w-4" /> Proses Payroll</Btn>
        {editable && <Btn variant="primary" data-testid="submit-period-button" disabled={busy || !payslips.length} onClick={() => act("submit", "Draft payroll diajukan ke Manager HRD")}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
        {isManager && pending && <Btn variant="outline" data-testid="reject-period-button" disabled={busy} onClick={() => setRejectOpen(true)} className="!border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak Draft</Btn>}
        {isManager && <Btn variant="success" data-testid="approve-all-button" disabled={busy || !pending} onClick={() => act("approve-all", "Semua slip di-approve & dikunci")} title={!pending ? "Periode harus diajukan dulu" : ""}><LockKeyhole className="h-4 w-4" /> Approve & Lock Semua</Btn>}
        <Btn variant="primary" data-testid="export-bsi-button" disabled={!approvedCount} onClick={exportBsi} title="Hanya slip approved"><Landmark className="h-4 w-4" /> Ekspor BSI (CSV)</Btn>
      </PageTitle>
      {period.status === "revision" && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3" data-testid="rejection-banner">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="text-sm">
            <div className="font-semibold">Draft ditolak oleh {period.rejected_by} — silakan koreksi lalu ajukan kembali</div>
            <div className="mt-1" data-testid="rejection-reason">Alasan: {period.rejection_reason}</div>
          </div>
        </div>
      )}
      {pending && (
        <div className="mb-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5" data-testid="pending-banner">
          Diajukan oleh {period.submitted_by}. {isManager ? "Silakan review, lalu Approve & Lock atau Tolak dengan alasan." : "Menunggu keputusan Manager HRD; data tidak dapat diubah."}
        </div>
      )}
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="payslips-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                {["NIK", "Nama", "Status", "PTKP / TER", "Poin Denda", "Bruto Komersial", "Bruto Pajak", "PPh 21", "Potongan", "THP", "Slip", ""].map((h, i) => (
                  <th key={h + i} className={`px-4 py-3 ${i > 3 && i < 10 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {payslips.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50" data-testid={`payslip-row-${s.employee.nik}`}>
                  <td className="px-4 py-3 num text-slate-600">{s.employee.nik}</td>
                  <td className="px-4 py-3 font-semibold">{s.employee.name}{s.is_manually_adjusted && <span className="ml-2 text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">EDIT</span>}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{PAYROLL_STATUS_LABELS[s.payroll_status]}</td>
                  <td className="px-4 py-3 num text-xs">{s.ptkp_status} · {s.ter_category} {s.ter_rate}%</td>
                  <td className={`px-4 py-3 num text-right ${s.late_penalty_points ? "text-rose-600 font-semibold" : ""}`}>{s.late_penalty_points}</td>
                  <td className="px-4 py-3 num text-right">{rp(s.gross_earnings)}</td>
                  <td className="px-4 py-3 num text-right text-slate-600">{rp(s.taxable_gross)}</td>
                  <td className="px-4 py-3 num text-right">{rp(s.pph21_amount)}</td>
                  <td className="px-4 py-3 num text-right text-rose-600">{rp(s.total_deductions)}</td>
                  <td className="px-4 py-3 num text-right font-bold text-emerald-600" data-testid={`thp-${s.employee.nik}`}>{rp(s.take_home_pay)}</td>
                  <td className="px-4 py-3"><StatusBadge map={SLIP_STATUS} status={s.status} /></td>
                  <td className="px-4 py-3 text-right"><Link to={`/hr-manager/payroll/${pid}/employee/${s.employee_id}`} data-testid={`review-${s.employee.nik}`} className="text-blue-900 font-semibold hover:underline whitespace-nowrap">Review</Link></td>
                </tr>
              ))}
              {!payslips.length && <tr><td colSpan={12} className="px-4 py-8 text-center text-slate-500">Belum ada slip. Klik "Proses Payroll".</td></tr>}
            </tbody>
            {!!payslips.length && (
              <tfoot className="bg-slate-50 font-semibold">
                <tr>
                  <td colSpan={5} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Total {payslips.length} karyawan</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("gross_earnings"))}</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("taxable_gross"))}</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("pph21_amount"))}</td>
                  <td className="px-4 py-3 num text-right text-rose-600">{rp(sum("total_deductions"))}</td>
                  <td className="px-4 py-3 num text-right text-emerald-600" data-testid="total-thp">{rp(sum("take_home_pay"))}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Panel>
      {!!period.review_history?.length && (
        <Panel title="Riwayat Review" className="mt-6">
          <div className="divide-y divide-slate-100 text-sm" data-testid="review-history">
            {[...period.review_history].reverse().map((h, i) => (
              <div key={i} className="px-5 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <History className="h-4 w-4 text-slate-400" />
                <span className={`font-semibold ${h.action === "rejected" ? "text-rose-600" : h.action === "approved" ? "text-emerald-600" : "text-slate-800"}`}>{ACTIONS[h.action] || h.action}</span>
                <span className="text-slate-500">oleh {h.by_name || h.by}</span>
                <span className="num text-xs text-slate-400">{new Date(h.at).toLocaleString("id-ID")}</span>
                {h.reason && <span className="w-full pl-7 text-slate-600">Alasan: {h.reason}</span>}
              </div>
            ))}
          </div>
        </Panel>
      )}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent data-testid="reject-dialog">
          <DialogHeader>
            <DialogTitle>Tolak Draft Payroll {period.period_name}</DialogTitle>
            <DialogDescription>Draft akan dikembalikan ke Staff HR untuk dikoreksi. Tuliskan alasan penolakan.</DialogDescription>
          </DialogHeader>
          <textarea data-testid="reject-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Contoh: Lembur Budi belum sesuai SPL, mohon dicek ulang." className="w-full border border-slate-300 rounded-md p-3 text-sm min-h-[110px]" />
          <div className="flex justify-end gap-2">
            <Btn variant="outline" data-testid="reject-cancel-button" onClick={() => setRejectOpen(false)}>Batal</Btn>
            <Btn data-testid="reject-confirm-button" disabled={busy || reason.trim().length < 5} onClick={reject} className="!bg-rose-600 hover:!bg-rose-700"><XCircle className="h-4 w-4" /> Tolak & Kembalikan</Btn>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
