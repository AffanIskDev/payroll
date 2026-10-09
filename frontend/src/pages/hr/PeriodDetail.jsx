import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Search, DownloadCloud, LockKeyhole, ChevronLeft, Landmark, Send, XCircle, AlertTriangle, History, Users, CalendarCheck, RotateCw, Smartphone, Car } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp, PERIOD_STATUS } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const COLS = ["NIK", "Nama", "PTKP", "Total Penghasilan", "PKP", "PPh 21", "Poin Presensi", "Poin Absensi", "Total Potongan", "Total BPJS Kesehatan", "Total BPJS TK", "Review"];

const ACTIONS = { submitted: "Diajukan ke Manager", rejected: "Ditolak", approved: "Approve & Lock" };

const nameList = (rows) => {
  const names = rows.slice(0, 8).map((r) => r.name).join(", ");
  return rows.length > 8 ? `${names}, dan ${rows.length - 8} lainnya` : names;
};

export default function PeriodDetail() {
  const { pid } = useParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [q, setQ] = useState("");
  const { user } = useAuth();
  const isManager = user?.role === "manager_hrd";
  const load = useCallback(() => api.get(`/hr/periods/${pid}`).then((r) => setD(r.data)), [pid]);
  useEffect(() => { load(); }, [load]);
  const sending = d?.payslips.some((s) => s.delivery_status === "queued");
  useEffect(() => {
    if (!sending) return undefined;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [sending, load]);

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
    if (await act("reject", "Draft dikembalikan ke Supervisor HRD untuk dikoreksi", { reason })) {
      setRejectOpen(false);
      setReason("");
    }
  };

  const exportBsi = async () => {
    try {
      const h = await saveFile("post", `/hr/periods/${pid}/export-bsi`, "BSI_Payroll.csv");
      const skipped = h["x-skipped-niks"];
      toast.success(`CSV BSI diunduh: ${h["x-exported-count"]} transfer${skipped ? ` · dilewati (Total Diterima 0 / tanpa rekening): ${skipped}` : ""}`);
    } catch (e) { toast.error(await blobErrMsg(e)); }
  };

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, payslips } = d;
  const editable = ["draft", "revision"].includes(period.status);
  const pending = period.status === "pending_approval";
  const approvedCount = payslips.filter((s) => s.status === "approved").length;
  const failed = payslips.filter((s) => s.delivery_status === "failed").length;
  const sentCount = payslips.filter((s) => s.delivery_status === "sent").length;
  const rows = payslips.filter((s) => (s.employee.name || "").toLowerCase().includes(q.trim().toLowerCase()));
  const sumRows = (k) => rows.reduce((a, s) => a + (s[k] || 0), 0);
  const missing = period.attendance_missing || [];
  const unlinked = period.attendance_unlinked || [];
  const skipped = period.employees_skipped || [];
  const ot = period.overtime_summary;
  const otNoRate = ot?.without_rate || [];
  const transport = period.components_summary;

  return (
    <div data-testid="period-detail-page">
      <Link to="/hr-manager/payroll" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua periode</Link>
      <PageTitle title={period.period_name} subtitle={`${period.start_date} → ${period.end_date} · Transfer ${period.payment_date || "-"}`}>
        <StatusBadge map={PERIOD_STATUS} status={period.status} testId="period-status-badge" />
        <Btn variant="outline" data-testid="fetch-attendance-button" disabled={busy || !editable} onClick={() => act("fetch-attendance", "Sinkron dari ROSY selesai & payroll dihitung ulang")} title="Karyawan & gaji, absensi, klaim lembur, dan Transport Homecare terbaru dari ROSY"><DownloadCloud className="h-4 w-4" /> {busy ? "Menyinkronkan..." : "Sinkron dari ROSY"}</Btn>
        {editable && <Btn variant="primary" data-testid="submit-period-button" disabled={busy || !payslips.length} onClick={() => act("submit", "Draft payroll diajukan ke Manager HRD")}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
        {isManager && pending && <Btn variant="outline" data-testid="reject-period-button" disabled={busy} onClick={() => setRejectOpen(true)} className="!border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak Draft</Btn>}
        {isManager && <Btn variant="success" data-testid="approve-all-button" disabled={busy || !pending} onClick={() => act("approve-all", "Semua slip di-approve & dikunci")} title={!pending ? "Periode harus diajukan dulu" : ""}><LockKeyhole className="h-4 w-4" /> Approve & Lock Semua</Btn>}
        {isManager && <Btn variant="primary" data-testid="export-bsi-button" disabled={!approvedCount} onClick={exportBsi} title="Hanya slip approved"><Landmark className="h-4 w-4" /> Ekspor BSI (CSV)</Btn>}
      </PageTitle>
      {period.last_sync_error && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3 text-sm" data-testid="sync-error-banner">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>Sinkron dari ROSY terakhir gagal: {period.last_sync_error}. Klik "Sinkron dari ROSY" untuk mencoba lagi — periode belum dapat diajukan sebelum sinkron berhasil.</span>
        </div>
      )}
      <div className="mb-4 grid sm:grid-cols-3 gap-3 text-sm" data-testid="sync-status">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-md px-4 py-2.5"><Users className="h-4 w-4 text-blue-900" /> Karyawan dari ROSY: <b className="num" data-testid="sync-employee-count">{period.employee_count ?? payslips.length}</b><span className="text-xs text-slate-500 num ml-auto">{period.employees_synced_at ? new Date(period.employees_synced_at).toLocaleString("id-ID") : "-"}</span></div>
        <div className={`flex items-center gap-2 border rounded-md px-4 py-2.5 ${period.attendance_synced_at ? "bg-white border-slate-200" : "bg-amber-50 border-amber-200 text-amber-900"}`}><CalendarCheck className="h-4 w-4 text-teal-700" /> {period.attendance_synced_at ? <>Absensi RUMATKU: <b className="num" data-testid="sync-attendance-count">{period.attendance_count} log</b><span className="text-xs text-slate-500 num ml-auto">{new Date(period.attendance_synced_at).toLocaleString("id-ID")}</span></> : <span data-testid="sync-attendance-pending">Absensi belum diambil — klik "Sinkron dari ROSY"</span>}</div>
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-md px-4 py-2.5" data-testid="transport-summary"><Car className="h-4 w-4 text-blue-900" /> Transport Homecare: {transport ? <><b className="num">{transport.transport_employees}</b> karyawan<span className="num ml-auto font-semibold">{rp(transport.transport_total)}</span></> : <span className="text-slate-500">belum disinkron</span>}</div>
      </div>
      {ot && (
        <div className={`mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 border rounded-md px-4 py-2.5 text-sm ${ot.pending || otNoRate.length ? "bg-amber-50 border-amber-200 text-amber-900" : "bg-white border-slate-200"}`} data-testid="overtime-summary">
          <span>Lembur dari ROSY (dibayar periode <span className="num">{ot.periode_bayar}</span>): <b className="num">{ot.claims}</b> klaim disetujui · <b className="num">{(ot.minutes / 60).toLocaleString("id-ID")}</b> jam · <b className="num">{ot.employees}</b> karyawan</span>
          {ot.pending > 0 && <span data-testid="overtime-pending">· <b className="num">{ot.pending}</b> klaim masih menunggu persetujuan HRD — belum masuk slip</span>}
          {otNoRate.length > 0 && <span data-testid="overtime-no-rate">· {otNoRate.length} karyawan punya jam lembur tapi tarifnya kosong, sehingga tidak dibayar: {nameList(otNoRate)}. Isi tarifnya di ROSY HRD (Gaji Karyawan → Atur Kontrak), lalu klik "Sinkron dari ROSY".</span>}
        </div>
      )}
      {(missing.length > 0 || unlinked.length > 0 || skipped.length > 0) && (
        <div className="mb-4 flex gap-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-3" data-testid="sync-warning-banner">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="text-sm space-y-1">
            {missing.length > 0 && <div data-testid="attendance-missing"><b className="num">{missing.length}</b> karyawan tanpa data absensi, sehingga Tunjangan Kehadirannya tidak terpotong apa pun: {nameList(missing)}</div>}
            {unlinked.length > 0 && <div data-testid="attendance-unlinked"><b className="num">{unlinked.length}</b> karyawan belum tertaut ke akun RUMATKU di HAM, jadi absensinya tidak terbaca: {nameList(unlinked)}</div>}
            {skipped.length > 0 && <div data-testid="employees-skipped"><b className="num">{skipped.length}</b> karyawan tidak ikut periode ini karena belum punya Kontrak Gaji di HAM: {nameList(skipped)}</div>}
          </div>
        </div>
      )}
      {period.status === "approved" && (
        <div className={`mb-4 flex flex-wrap items-center gap-3 border rounded-md px-4 py-2.5 text-sm ${failed ? "bg-rose-50 border-rose-200 text-rose-800" : "bg-white border-slate-200"}`} data-testid="delivery-banner">
          <Smartphone className="h-4 w-4 text-teal-700" />
          <span>Slip PDF ke aplikasi Rumatku: <b className="num" data-testid="delivery-sent-count">{sentCount}/{payslips.length}</b> terkirim{sending && " · sedang mengirim..."}{failed > 0 && <> · <b data-testid="delivery-failed-count">{failed}</b> gagal setelah 3x percobaan otomatis</>}</span>
          {failed > 0 && isManager && <Btn variant="outline" data-testid="resend-failed-button" disabled={busy || sending} onClick={() => act("resend-failed", "Slip gagal dikirim ulang ke Rumatku")} className="ml-auto"><RotateCw className="h-4 w-4" /> Kirim Ulang Semua yang Gagal</Btn>}
        </div>
      )}
      {period.status === "revision" && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3" data-testid="rejection-banner">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="text-sm">
            <div className="font-semibold">Draft ditolak oleh {period.rejected_by_name || period.rejected_by} — silakan koreksi lalu ajukan kembali</div>
            <div className="mt-1" data-testid="rejection-reason">Alasan: {period.rejection_reason}</div>
          </div>
        </div>
      )}
      {pending && (
        <div className="mb-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5" data-testid="pending-banner">
          Diajukan oleh {period.submitted_by_name || period.submitted_by}. {isManager ? "Silakan review, lalu Approve & Lock atau Tolak dengan alasan." : "Menunggu keputusan Manager HRD; data tidak dapat diubah."}
        </div>
      )}
      <Panel>
        <div className="overflow-x-auto">
          <label className="mb-3 flex items-center gap-2 border border-slate-300 rounded-md px-3 py-1.5 bg-white w-72">
            <Search className="h-4 w-4 text-slate-400" />
            <input data-testid="payslip-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama karyawan" className="outline-none text-sm w-full" />
          </label>
          <table className="w-full text-sm" data-testid="payslips-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                {COLS.map((h, i) => (
                  <th key={h + i} className={`px-4 py-3 ${i > 2 && i < 11 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50" data-testid={`payslip-row-${s.employee.nik}`}>
                  <td className="px-4 py-3 num text-slate-600">{s.employee.nik}</td>
                  <td className="px-4 py-3 font-semibold">{s.employee.name}{s.is_manually_adjusted && <span className="ml-2 text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">EDIT</span>}</td>
                  <td className="px-4 py-3 num text-xs">{s.ptkp_status}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.gross_earnings)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap text-slate-600">{rp(s.taxable_gross)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.pph21_amount)}</td>
                  <td className={`px-4 py-3 num text-right ${s.late_penalty_points ? "text-rose-600 font-semibold" : ""}`} data-testid={`poin-presensi-${s.employee.nik}`}>{s.late_penalty_points}</td>
                  <td className={`px-4 py-3 num text-right ${s.absence_points ? "text-rose-600 font-semibold" : ""}`} data-testid={`poin-absensi-${s.employee.nik}`}>{s.absence_points ?? 0}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap text-rose-600">{rp(s.total_deductions)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.iuran_bpjs_kes_total)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.iuran_bpjs_tk_total)}</td>
                  <td className="px-4 py-3 text-right"><Link to={`/hr-manager/payroll/${pid}/employee/${s.employee_id}`} data-testid={`review-${s.employee.nik}`} className="text-blue-900 font-semibold hover:underline whitespace-nowrap">Review</Link></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{payslips.length ? "Tidak ada nama yang cocok." : "Belum ada slip. Klik \"Sinkron dari ROSY\"."}</td></tr>}
            </tbody>
            {!!rows.length && (
              <tfoot className="bg-slate-50 font-semibold">
                <tr>
                  <td colSpan={3} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Total {rows.length} karyawan</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(sumRows("gross_earnings"))}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(sumRows("taxable_gross"))}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(sumRows("pph21_amount"))}</td>
                  <td />
                  <td />
                  <td className="px-4 py-3 num text-right whitespace-nowrap text-rose-600">{rp(sumRows("total_deductions"))}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(sumRows("iuran_bpjs_kes_total"))}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(sumRows("iuran_bpjs_tk_total"))}</td>
                  <td />
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
            <DialogDescription>Draft akan dikembalikan ke Supervisor HRD untuk dikoreksi. Tuliskan alasan penolakan.</DialogDescription>
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
