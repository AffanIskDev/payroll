import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Search, DownloadCloud, LockKeyhole, ChevronLeft, ChevronDown, Landmark, Send, XCircle, AlertTriangle, History, Users, Clock, Ban, Baby, Hourglass, RotateCw, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp, PERIOD_STATUS, formatDate, formatDateRange, jamMenit, unfinishedSyncDay } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn, SummaryCard } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import SyncTodayDialog from "@/components/SyncTodayDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

// NIK & PTKP digabung ke kolom Karyawan (baris kedua) supaya tabel muat tanpa digeser ke samping
const COLS = ["Karyawan", "Total Penghasilan", "PKP", "PPh 21", "Poin Presensi", "Poin Absensi", "Total Potongan", "Total BPJS Kesehatan", "Total BPJS TK", "Review"];
// kolom Karyawan menempel di kiri saat tabel digeser di HP/tablet (12 Okt 2026); garis tipis memisahkannya dari angka
const STICKY = "sticky left-0 z-10 shadow-[1px_0_0_#e2e8f0]";

const ACTIONS = { submitted: "Diajukan ke Manager", rejected: "Ditolak", approved: "Lock & Approve" };

const FILTER_LABELS = { overtime: "Lembur", unpaid: "Unpaid", maternity: "Cuti Melahirkan", partial: "Tidak Penuh" };

const nameList = (rows) => {
  const names = rows.slice(0, 8).map((r) => r.name).join(", ");
  return rows.length > 8 ? `${names}, dan ${rows.length - 8} lainnya` : names;
};

export default function PeriodDetail() {
  const { pid } = useParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchProblems, setBatchProblems] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [confirmDay, setConfirmDay] = useState(null);
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
  const approveAll = async () => {
    if (await act("approve-all", "Semua slip dikunci & di-approve")) setApproveOpen(false);
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

  // Batch Payment BSI (TXT, format ROSY): the answer is either the file or the list of data to fix first — that list
  // is the point of the all-or-nothing rule, so it gets its own dialog instead of a toast
  const exportBatch = async () => {
    setBatchBusy(true);
    try {
      const h = await saveFile("post", `/hr/periods/${pid}/export-batch-bsi`, "BatchPayment.txt");
      const skippedNiks = (h["x-skipped-niks"] || "").split(",").filter(Boolean);
      const skippedNames = d.payslips.filter((s) => skippedNiks.includes(s.employee.nik)).map((s) => s.employee.name);
      setBatchOpen(false);
      toast.success(`Berkas Batch Payment diunduh: ${h["x-exported-count"]} transfer, total ${rp(h["x-total-amount"])}${skippedNames.length ? ` · tidak ditransfer (cuti tanpa upah, Rp 0): ${skippedNames.join(", ")}` : ""}`);
    } catch (e) {
      let body = null;
      if (e?.response?.data instanceof Blob) {
        try { body = JSON.parse(await e.response.data.text()); } catch { body = null; }
      }
      if (body?.problems?.length) {
        setBatchOpen(false);
        setBatchProblems(body.problems);
      } else toast.error(typeof body?.detail === "string" ? body.detail : errMsg(e));
    } finally { setBatchBusy(false); }
  };

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, payslips, summary, signer_status: signerStatus } = d;
  const noSignature = signerStatus && signerStatus !== "ada";
  const editable = ["draft", "revision"].includes(period.status);

  // Tombol "Fetch Data Terbaru" (dulu "Sinkron dari ROSY") kembali ke halaman ini (user 13 Okt 2026), sebelumnya di Dashboard: satu tombol mengambil karyawan
  // & gaji, absensi, klaim lembur, dan Tambahan Bulanan ROSY, lalu menghitung ulang slip
  const sync = async () => {
    setConfirmDay(null);
    setSyncing(true);
    try { await act("fetch-attendance", `Sinkron ${period.period_name} dari ROSY selesai & payroll dihitung ulang`); } finally { setSyncing(false); }
  };
  // periode yang masih berjalan: tanya dulu, karena absensi hari ini belum selesai (user 12 Okt 2026)
  const requestSync = () => {
    const day = unfinishedSyncDay(period.start_date, period.end_date);
    if (day) setConfirmDay(day);
    else sync();
  };
  const pending = period.status === "pending_approval";
  const approvedCount = payslips.filter((s) => s.status === "approved").length;
  const failed = payslips.filter((s) => s.delivery_status === "failed").length;
  const sentCount = payslips.filter((s) => s.delivery_status === "sent").length;
  const nameById = Object.fromEntries(payslips.map((s) => [s.employee_id, s.employee.name]));
  const namesOf = (ids) => ids.map((id) => nameById[id] || id);
  // a card filters the table to its employees; one with nobody in it is not clickable
  const card = (key) => ({ active: filter === key, onClick: summary?.[key]?.length ? () => setFilter(filter === key ? null : key) : undefined });
  const only = filter && summary ? new Set(summary[filter]) : null;
  const rows = payslips.filter((s) => (!only || only.has(s.employee_id)) && (s.employee.name || "").toLowerCase().includes(q.trim().toLowerCase()));
  const sumRows = (k) => rows.reduce((a, s) => a + (s[k] || 0), 0);
  const missing = period.attendance_missing || [];
  const unlinked = period.attendance_unlinked || [];
  const ot = period.overtime_summary;
  const otNoRate = ot?.without_rate || [];
  const batchGroups = (batchProblems || []).reduce((g, p) => ({ ...g, [p.kind]: [...(g[p.kind] || []), p] }), {});

  return (
    <div data-testid="period-detail-page">
      <Link to="/hr-manager/payroll" className="tap inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua periode</Link>
      <PageTitle title={period.period_name} titleExtra={<StatusBadge map={PERIOD_STATUS} status={period.status} caption="Status:" large testId="period-status-badge" />} subtitle={<>
        <span className="block" data-testid="period-range">{formatDateRange(period.start_date, period.end_date)}</span>
        <span className="block" data-testid="period-transfer">Transfer: {formatDate(period.payment_date)}</span>
        <span className="block" data-testid="period-sync-status">Sinkron terakhir: {period.last_sync_at ? new Date(period.last_sync_at).toLocaleString("id-ID") : "belum pernah"}</span>
      </>}>
        <Btn variant="outline" data-testid="fetch-attendance-button" disabled={busy || !editable} onClick={requestSync} title={editable ? "Karyawan & gaji, absensi, klaim lembur, dan Tambahan Bulanan (Transport, Bonus, THR, Potongan Target, Cicilan) terbaru dari ROSY" : "Periode ini sudah diajukan atau dikunci, jadi tidak bisa disinkron lagi"}><DownloadCloud className={`h-4 w-4 ${syncing ? "animate-pulse" : ""}`} /> {syncing ? "Menyinkronkan..." : "Fetch Data Terbaru"}</Btn>
        {!isManager && editable && <Btn variant="primary" data-testid="submit-period-button" disabled={busy || !payslips.length} onClick={() => act("submit", "Draft payroll diajukan ke Manager HRD")}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
        {isManager && pending && <Btn variant="outline" data-testid="reject-period-button" disabled={busy} onClick={() => setRejectOpen(true)} className="!border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak Draft</Btn>}
        {isManager && (
          // modal={false}: dialog Batch Payment dibuka dari menu ini; menu modal Radix bisa meninggalkan body tak bisa diklik
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger data-testid="export-bsi-menu" disabled={!payslips.length} className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-50"><Landmark className="h-4 w-4" /> Export BSI <ChevronDown className="h-4 w-4" /></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80">
              <DropdownMenuItem data-testid="export-batch-bsi-button" onSelect={() => setBatchOpen(true)} className="flex-col items-start gap-0.5 cursor-pointer">
                <span className="font-semibold">TXT — Batch Payment BSI</span>
                <span className="text-xs text-slate-500">Format unggah BSI, sama dengan ROSY; slip draft ikut diekspor</span>
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="export-bsi-button" disabled={!approvedCount} onSelect={exportBsi} className="flex-col items-start gap-0.5 cursor-pointer">
                <span className="font-semibold">CSV</span>
                <span className="text-xs text-slate-500">{approvedCount ? "Hanya slip yang sudah di-approve" : "Hanya slip yang sudah di-approve — belum ada"}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {isManager && <Btn variant="success" data-testid="approve-all-button" disabled={busy || period.status === "approved"} onClick={() => setApproveOpen(true)} title={period.status === "approved" ? "Periode sudah dikunci & di-approve" : ""}><LockKeyhole className="h-4 w-4" /> Lock & Approve</Btn>}
      </PageTitle>
      {period.last_sync_error && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3 text-sm" data-testid="sync-error-banner">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>Sinkron dari ROSY terakhir gagal: {period.last_sync_error}. Ulangi lewat tombol "Fetch Data Terbaru" di atas — periode belum dapat diajukan sebelum sinkron berhasil.</span>
        </div>
      )}
      {summary && (
        <div className="mb-4 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3" data-testid="period-summary">
          <SummaryCard icon={Users} label="Ikut Digaji" value={summary.included} sub="karyawan di periode ini" active={!filter} onClick={() => setFilter(null)} testId="sum-included" />
          <SummaryCard icon={Clock} label="Lembur" value={summary.overtime.length} names={namesOf(summary.overtime)} sub={`${jamMenit(summary.overtime_hours)} · ${rp(summary.overtime_pay)}`} {...card("overtime")} testId="sum-overtime" />
          <SummaryCard icon={Ban} label="Unpaid" value={summary.unpaid.length} names={namesOf(summary.unpaid)} sub="cuti di luar tanggungan" warn {...card("unpaid")} testId="sum-unpaid" />
          <SummaryCard icon={Baby} label="Cuti Melahirkan" value={summary.maternity.length} names={namesOf(summary.maternity)} sub="Tunj. Kehadiran terpotong" {...card("maternity")} testId="sum-maternity" />
          <SummaryCard icon={Hourglass} label="Tidak Penuh" value={summary.partial.length} names={namesOf(summary.partial)} sub="gaji prorata" warn {...card("partial")} testId="sum-partial" />
        </div>
      )}
      {!period.attendance_synced_at && <div className="mb-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5" data-testid="sync-attendance-pending">Absensi belum diambil — klik "Fetch Data Terbaru".</div>}
      {noSignature && period.status !== "approved" && (
        <div className="mb-4 flex items-center gap-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5 text-sm" data-testid="signer-missing-banner">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{signerStatus === "tanpa_penandatangan" ? "Belum ada penandatangan slip" : "Gambar tanda tangan penandatangan belum ada"} — slip yang di-approve akan terbit <b>tanpa tanda tangan</b>. Cek di Konfigurasi → Penandatangan Slip Gaji.</span>
        </div>
      )}
      {(ot?.pending > 0 || otNoRate.length > 0) && (
        <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 border rounded-md px-4 py-2.5 text-sm bg-amber-50 border-amber-200 text-amber-900" data-testid="overtime-summary">
          <AlertTriangle className="h-4 w-4" />
          {ot.pending > 0 && <span data-testid="overtime-pending"><b className="num">{ot.pending}</b> klaim masih menunggu persetujuan HRD — belum masuk slip</span>}
          {otNoRate.length > 0 && <span data-testid="overtime-no-rate">{otNoRate.length} karyawan punya jam lembur tapi tarifnya kosong, sehingga tidak dibayar: {nameList(otNoRate)}. Isi tarifnya di ROSY HRD (Gaji Karyawan → Atur Kontrak), lalu klik "Fetch Data Terbaru".</span>}
        </div>
      )}
      {(missing.length > 0 || unlinked.length > 0) && (
        <div className="mb-4 flex gap-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-3" data-testid="sync-warning-banner">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="text-sm space-y-1">
            {missing.length > 0 && <div data-testid="attendance-missing"><b className="num">{missing.length}</b> karyawan tanpa data absensi, sehingga Tunjangan Kehadirannya tidak terpotong apa pun: {nameList(missing)}</div>}
            {unlinked.length > 0 && <div data-testid="attendance-unlinked"><b className="num">{unlinked.length}</b> karyawan belum tertaut ke akun RUMATKU di HAM, jadi absensinya tidak terbaca: {nameList(unlinked)}</div>}
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
          {(period.submitted_by_name || period.submitted_by) && <>Diajukan oleh {period.submitted_by_name || period.submitted_by}. </>}{isManager ? "Silakan review, lalu Lock & Approve atau Tolak dengan alasan." : "Menunggu keputusan Manager HRD; data tidak dapat diubah."}
        </div>
      )}
      <Panel>
        {/* bilah cari diberi ruang napas & dipisah garis dari tabel, tidak menempel ke tepi panel (user 12 Okt 2026) */}
        <div className="px-5 py-4 border-b border-slate-200 flex flex-wrap items-center gap-3" data-testid="payslip-toolbar">
          <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-2 bg-white w-full sm:w-80 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-900/10">
            <Search className="h-4 w-4 text-slate-400" />
            <input data-testid="payslip-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama karyawan" className="outline-none text-sm w-full" />
          </label>
          {filter && (
            <span className="inline-flex items-center gap-2 text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-3 py-2" data-testid="payslip-filter">
              Filter: <b>{FILTER_LABELS[filter]}</b> · <span className="num">{only.size}</span> karyawan
              <button type="button" onClick={() => setFilter(null)} className="tap text-blue-900 hover:text-rose-600" title="Hapus filter" data-testid="payslip-filter-clear"><XCircle className="h-4 w-4" /></button>
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="payslips-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                {COLS.map((h, i) => (
                  <th key={h + i} className={`px-4 py-3 ${i > 0 && i < COLS.length - 1 ? "text-right" : "text-left"} ${i === 0 ? STICKY : ""} ${i === 0 ? "bg-slate-50" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((s) => (
                <tr key={s.id} className="group hover:bg-slate-50" data-testid={`payslip-row-${s.employee.nik}`}>
                  <td className={`px-4 py-2.5 min-w-[11rem] bg-white group-hover:bg-slate-50 ${STICKY}`}>
                    <div className="font-semibold leading-snug">
                      <Link to={`/hr-manager/payroll/${pid}/employee/${s.employee_id}`} className="tap text-slate-900 hover:text-blue-900 hover:underline">{s.employee.name}</Link>
                      {s.is_manually_adjusted && <span className="ml-2 text-[11px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">EDIT</span>}
                    </div>
                    <div className="num text-xs text-slate-500 whitespace-nowrap">{s.employee.nik} · {s.ptkp_status}</div>
                  </td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.gross_earnings)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap text-slate-600">{rp(s.taxable_gross)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.pph21_amount)}</td>
                  <td className={`px-4 py-3 num text-right ${s.late_penalty_points ? "text-rose-600 font-semibold" : ""}`} data-testid={`poin-presensi-${s.employee.nik}`}>{s.late_penalty_points}</td>
                  <td className={`px-4 py-3 num text-right ${s.absence_points ? "text-rose-600 font-semibold" : ""}`} data-testid={`poin-absensi-${s.employee.nik}`}>{s.absence_points ?? 0}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap text-rose-600">{rp(s.total_deductions)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.iuran_bpjs_kes_total)}</td>
                  <td className="px-4 py-3 num text-right whitespace-nowrap">{rp(s.iuran_bpjs_tk_total)}</td>
                  <td className="px-4 py-3 text-right"><Link to={`/hr-manager/payroll/${pid}/employee/${s.employee_id}`} data-testid={`review-${s.employee.nik}`} className="tap text-blue-900 font-semibold hover:underline whitespace-nowrap">Review</Link></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{payslips.length ? "Tidak ada nama yang cocok." : "Belum ada slip. Klik \"Fetch Data Terbaru\"."}</td></tr>}
            </tbody>
            {!!rows.length && (
              <tfoot className="bg-slate-50 font-semibold">
                <tr>
                  <td className={`px-4 py-3 text-xs uppercase tracking-wider text-slate-500 whitespace-nowrap bg-slate-50 ${STICKY}`}>Total {rows.length} karyawan</td>
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
      <SyncTodayDialog day={confirmDay} periodName={period.period_name} onConfirm={sync} onCancel={() => setConfirmDay(null)} />
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
      <Dialog open={approveOpen} onOpenChange={(o) => !busy && setApproveOpen(o)}>
        <DialogContent data-testid="approve-confirm-dialog">
          <DialogHeader>
            <DialogTitle>Lock & Approve semua slip {period.period_name}?</DialogTitle>
            <DialogDescription><span className="num">{payslips.length}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(payslips.reduce((a, s) => a + (s.take_home_pay || 0), 0))}</b></DialogDescription>
          </DialogHeader>
          <div className="text-sm text-slate-600 space-y-2">
            {editable && <p className="bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2" data-testid="approve-direct-note">Periode ini belum diajukan Supervisor HRD — Anda meng-approve langsung dari draft.</p>}
            {noSignature && <p className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-3 py-2" data-testid="approve-no-signature-note">Tanda tangan penandatangan belum ada — slip PDF akan terbit <b>tanpa tanda tangan</b>.</p>}
            <p>Semua slip <b>dikunci dan tidak bisa diubah atau dibuka lagi</b>. Slip PDF otomatis dikirim ke aplikasi Rumatku karyawan.</p>
          </div>
          <div className="flex justify-end gap-2">
            <Btn variant="outline" data-testid="approve-cancel-button" disabled={busy} onClick={() => setApproveOpen(false)}>Batal</Btn>
            <Btn variant="success" data-testid="approve-confirm-button" disabled={busy} onClick={approveAll}><LockKeyhole className="h-4 w-4" /> {busy ? "Mengunci..." : "Ya, Lock & Approve"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={batchOpen} onOpenChange={(o) => !batchBusy && setBatchOpen(o)}>
        <DialogContent data-testid="batch-confirm-dialog">
          <DialogHeader>
            <DialogTitle>Buat berkas Batch Payment BSI?</DialogTitle>
            <DialogDescription>Periode <b>{period.period_name}</b> · <span className="num">{payslips.length}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(payslips.reduce((a, s) => a + (s.take_home_pay || 0), 0))}</b></DialogDescription>
          </DialogHeader>
          <div className="text-sm text-slate-600 space-y-2">
            <p>Berkas TXT ini diunggah ke Batch Payment BSI dan <b>memindahkan uang</b>. Nominal diambil dari slip periode ini; rekening dan nama dari data karyawan ROSY (sinkron terakhir).</p>
            {payslips.length > approvedCount && <p className="bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2" data-testid="batch-draft-warning"><b className="num">{payslips.length - approvedCount}</b> dari <span className="num">{payslips.length}</span> slip belum di-approve dan <b>ikut diekspor</b>. Angkanya masih bisa berubah (sinkron ulang atau koreksi), jadi unduh berkas tepat sebelum diunggah ke bank.</p>}
            <p>Hanya rekening <b>BSI</b>. Kalau ada satu saja data yang bermasalah, berkasnya tidak dibuat dan daftarnya ditampilkan.</p>
          </div>
          <div className="flex justify-end gap-2">
            <Btn variant="outline" data-testid="batch-cancel-button" disabled={batchBusy} onClick={() => setBatchOpen(false)}>Batal</Btn>
            <Btn variant="success" data-testid="batch-confirm-button" disabled={batchBusy} onClick={exportBatch}><Landmark className="h-4 w-4" /> {batchBusy ? "Menyiapkan berkas..." : "Ya, Buat Berkas"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={!!batchProblems} onOpenChange={(o) => !o && setBatchProblems(null)}>
        <DialogContent className="max-w-2xl" data-testid="batch-problems-dialog">
          <DialogHeader>
            <DialogTitle>Ada {batchProblems?.length} data yang harus dibetulkan</DialogTitle>
            <DialogDescription>Berkas <b>tidak dibuat</b>. Satu baris salah berarti uang masuk ke rekening yang keliru, jadi seluruh temuan harus dibereskan dulu: betulkan data karyawannya di ROSY HRD, klik "Fetch Data Terbaru" di halaman ini, lalu buat ulang berkasnya.</DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] overflow-y-auto text-sm space-y-3">
            {Object.entries(batchGroups).map(([kind, list]) => (
              <div key={kind}>
                <div className="font-semibold">{kind} <span className="font-normal text-slate-400">({list.length})</span></div>
                <ul className="list-disc pl-5 text-slate-700">
                  {list.map((p, i) => <li key={i}>{p.name} <span className="num text-xs text-slate-400">{p.nik}</span> — {p.note}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <div className="flex justify-end">
            <Btn data-testid="batch-problems-close" onClick={() => setBatchProblems(null)}>Mengerti</Btn>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
