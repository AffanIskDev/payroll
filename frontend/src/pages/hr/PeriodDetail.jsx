import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Search, DownloadCloud, LockKeyhole, ChevronLeft, ChevronRight, ChevronDown, Landmark, Send, XCircle, AlertTriangle, History, RotateCw, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp, formatDate, formatDateRange, jamMenit, unfinishedSyncDay } from "@/lib/format";
import { PageTitle, Panel, PeriodStatusChip, Btn, KpiCard, FilterTab } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import SyncTodayDialog from "@/components/SyncTodayDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

// Halaman periode bergaya "Payroll Control Tower" (contoh tampilan dari user 15 Okt 2026: banyak angka & tombol yang
// menonjol): kepala periode + tombol aksi, 4 kartu nominal, banner peringatan, lalu tabel review berwarna.

// Kolom tabel TETAP seperti semula — user 15 Okt 2026: "urutan kolom tablenya jangan diubah, hanya desain dan warnanya".
// NIK & PTKP digabung ke kolom Karyawan (baris kedua) supaya tabel muat tanpa digeser ke samping
const COLS = ["Karyawan", "Total Penghasilan", "PKP", "PPh 21", "Poin Presensi", "Poin Absensi", "Total Potongan", "Total BPJS Kesehatan", "Total BPJS TK", "Review"];
// kolom Karyawan menempel di kiri saat tabel digeser di HP/tablet (12 Okt 2026); garis tipis memisahkannya dari angka
const STICKY = "sticky left-0 z-10 shadow-[1px_0_0_#e2e8f0]";
// kolom rupiah, urut sesuai kolom; null = kolom poin (tanpa total rupiah). Desain RUMAT: tanpa warna per jenis angka —
// potongan rutin (PPh, BPJS, Total Potongan) slate, merah hanya untuk poin denda
const MONEY = [
  ["gross_earnings", "text-slate-900"],
  ["taxable_gross", "text-slate-600"],
  ["pph21_amount", "text-slate-900"],
  null,
  null,
  ["total_deductions", "text-slate-700"],
  ["iuran_bpjs_kes_total", "text-slate-900"],
  ["iuran_bpjs_tk_total", "text-slate-900"],
];

const ACTIONS = { submitted: "Diajukan ke Manager", rejected: "Ditolak", approved: "Lock & Approve" };


const FILTER_LABELS = { overtime: "Lembur", unpaid: "Unpaid", maternity: "Cuti Melahirkan", partial: "Tidak Penuh", bank: "Rekening Belum Siap" };

const nameList = (rows) => {
  const names = rows.slice(0, 8).map((r) => r.name).join(", ");
  return rows.length > 8 ? `${names}, dan ${rows.length - 8} lainnya` : names;
};

// Tampilan tabel (cari, departemen, filter, halaman) diingat per periode selama tab terbuka, supaya kembali dari Review
// ke posisi yang sama; baris per halaman diingat di peramban ini. Penyimpanan ditolak peramban → pakai bawaan.
const viewKey = (pid) => `rasa.periode.${pid}`;
const readView = (pid) => {
  try { return JSON.parse(sessionStorage.getItem(viewKey(pid))) || {}; } catch { return {}; }
};
const PER_PAGE_KEY = "rasa.periode.perHalaman";
const PER_PAGE = [25, 50, 100, 0]; // 0 = semua
const readPerPage = () => {
  try {
    const v = localStorage.getItem(PER_PAGE_KEY);
    return v !== null && PER_PAGE.includes(Number(v)) ? Number(v) : 50;
  } catch { return 50; }
};
// sampai 7 halaman semua nomor tampil; lebih dari itu: 1 … 4 5 [6] 7 … 10
const pageItems = (cur, total) => {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const keep = [...new Set([1, cur - 1, cur, cur + 1, total])].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  return keep.flatMap((p, i) => (i && p - keep[i - 1] > 1 ? [`gap-${p}`, p] : [p]));
};

// angka 0 dipudarkan supaya yang berisi menonjol
const RpCell = ({ v, tone }) => <td className={`px-3 py-3 num text-right whitespace-nowrap ${v ? tone : "text-slate-400"}`}>{rp(v)}</td>;

const PageBtn = ({ active, className = "", ...p }) => (
  <button type="button" {...p} className={`tap inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border px-2 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? "border-brand-700 bg-brand-700 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"} ${className}`} />
);

export default function PeriodDetailPage() {
  const { pid } = useParams();
  // key: pindah periode = tampilan tabel periode itu sendiri
  return <PeriodDetail key={pid} pid={pid} />;
}

function PeriodDetail({ pid }) {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [q, setQ] = useState(() => readView(pid).q || "");
  const [dept, setDept] = useState(() => readView(pid).dept || "");
  const [filter, setFilter] = useState(() => readView(pid).filter || null);
  const [page, setPage] = useState(() => readView(pid).page || 1);
  const [perPage, setPerPage] = useState(readPerPage);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchProblems, setBatchProblems] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [confirmDay, setConfirmDay] = useState(null);
  const [bankOpen, setBankOpen] = useState(false);
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
  useEffect(() => {
    try { sessionStorage.setItem(viewKey(pid), JSON.stringify({ q, dept, filter, page })); } catch { /* tanpa penyimpanan: tetap jalan */ }
  }, [pid, q, dept, filter, page]);

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
  // Rekening yang belum bisa dibayar lewat Batch Payment BSI (no. rekening / nama di rekening kosong, bukan BSI, format
  // salah) memblokir Lock & Approve (user 14 Okt 2026) dan juga Ajukan ke Manager ("ajukan ke manager juga diblokir") —
  // backend menolak keduanya; di sini banner, filter, badge baris & kedua tombol nonaktif
  const blockers = d.bank_blockers || [];
  const blocked = blockers.length > 0 && period.status !== "approved";
  const blockerById = Object.fromEntries(blockers.map((b) => [b.employee_id, b]));
  const blockerKinds = Object.entries(blockers.reduce((m, b) => {
    b.problems.forEach((p) => { m[p.kind] = (m[p.kind] || 0) + 1; });
    return m;
  }, {})).sort((a, b) => b[1] - a[1]);

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
  const slipById = Object.fromEntries(payslips.map((s) => [s.employee_id, s]));
  const namesOf = (ids) => ids.map((id) => slipById[id]?.employee.name || id);
  const missing = period.attendance_missing || [];
  const unlinked = period.attendance_unlinked || [];
  const ot = period.overtime_summary;
  const otNoRate = ot?.without_rate || [];
  const batchGroups = (batchProblems || []).reduce((g, p) => ({ ...g, [p.kind]: [...(g[p.kind] || []), p] }), {});

  // kartu nominal (seluruh periode)
  const sum = (f) => payslips.reduce((a, s) => a + (f(s) || 0), 0);
  const kpi = {
    thp: sum((s) => s.take_home_pay), gross: sum((s) => s.gross_earnings), pph: sum((s) => s.pph21_amount),
    bpjsCo: sum((s) => (s.tunjangan_bpjs_kes || 0) + (s.tunjangan_bpjs_tk || 0)),
    kes: sum((s) => s.iuran_bpjs_kes_total), tk: sum((s) => s.iuran_bpjs_tk_total),
  };
  const taxed = payslips.filter((s) => s.pph21_amount > 0).length;
  const december = payslips.some((s) => s.pph21_method === "pasal17");
  const wd = payslips[0]?.work_days || 25;
  const kotor = payslips[0]?.pph21_basis === "kotor";

  // filter dari tab (dulu kartu, user 10 Okt 2026); filter yang tersimpan tapi kelompoknya kini kosong diabaikan
  const activeFilter = filter && summary?.[filter]?.length ? filter : null;
  const only = activeFilter ? new Set(summary[activeFilter]) : null;
  const term = q.trim().toLowerCase();
  const rows = payslips.filter((s) => (!only || only.has(s.employee_id)) && (!dept || s.employee.department === dept)
    && (!term || (s.employee.name || "").toLowerCase().includes(term) || (s.employee.nik || "").toLowerCase().includes(term)
      || (s.doc_number || "").toLowerCase().includes(term)));  // nomor dokumen slip approved (15 Okt 2026): telusur dari slip/QR
  const pageCount = perPage ? Math.max(1, Math.ceil(rows.length / perPage)) : 1;
  const cur = Math.min(page, pageCount);
  const pageRows = perPage ? rows.slice((cur - 1) * perPage, cur * perPage) : rows;
  const depts = [...new Set(payslips.map((s) => s.employee.department).filter(Boolean))].sort();
  const toTable = () => document.getElementById("payslip-review")?.scrollIntoView({ behavior: "smooth", block: "start" });
  const applyFilter = (key) => {
    setFilter(key);
    setPage(1);
  };
  const goPage = (p) => {
    setPage(p);
    toTable();
  };

  const unpaidIds = summary?.unpaid || [];
  const maternityIds = summary?.maternity || [];
  const partialIds = summary?.partial || [];
  // keterangan di baris filter = sub-teks kartu filter lama (10 & 14 Okt 2026)
  const filterHint = {
    overtime: <><span className="num">{jamMenit(summary?.overtime_hours)}</span> · <span className="num">{rp(summary?.overtime_pay)}</span></>,
    unpaid: "cuti di luar tanggungan",
    maternity: "dibayar gaji pokok",
    partial: "gaji prorata",
    bank: period.status === "approved" ? "dicek saat Lock & Approve" : isManager ? "blokir Lock & Approve" : "blokir Ajukan ke Manager",
  }[activeFilter];

  const tabs = [
    [null, "Semua", payslips.length, "sum-included"],
    ["overtime", "Lembur", summary?.overtime?.length || 0, "sum-overtime"],
    ["unpaid", "Unpaid", unpaidIds.length, "sum-unpaid"],
    ["maternity", "Cuti Melahirkan", maternityIds.length, "sum-maternity"],
    ["partial", "Tidak Penuh", partialIds.length, "sum-partial"],
    ["bank", "Rekening Belum Siap", summary?.bank?.length || 0, "sum-bank", true],
  ];
  const syncedAt = period.last_sync_at ? new Date(period.last_sync_at).toLocaleString("id-ID") : "belum pernah";
  const actionTitle = blocked ? `Diblokir: rekening ${blockers.length} karyawan belum siap dibayar lewat BSI` : "";

  return (
    <div data-testid="period-detail-page">
      <Link to="/hr-manager/payroll" className="tap inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua periode</Link>

      {/* Kepala halaman = PageTitle standar desain RUMAT (15 Okt 2026): status di samping judul (user 13 Okt 2026); tombol maks.
          3 gaya — outline (Fetch, Export), primary teal (Ajukan, Lock & Approve), bahaya (Tolak). Paling banyak 3 tombol sebaris
          (user 15 Okt 2026: "dibuat 3 saja sebaris", tombol Hitung Ulang Semua dibuang): Fetch hanya tampil selagi periode masih
          bisa diubah — sesudah diajukan/dikunci tombol itu memang nonaktif. Di HP tiap tombol memenuhi barisnya. */}
      <PageTitle title={`Periode Gaji: ${period.period_name}`}
        // status = lencana (user 15 Okt 2026: "statusnya diubah lagi"), komponen yang sama dengan Dashboard
        titleExtra={<PeriodStatusChip status={period.status} testId="period-status-badge" />}
        // rentang & transfer satu baris, sinkron terakhir baris kedua — tetap rapi berapa pun lebar layarnya (tanpa "|" menggantung)
        subtitle={<>
          <span className="block">
            <span className="block sm:inline whitespace-nowrap" data-testid="period-range">Rentang: <span className="text-slate-700">{formatDateRange(period.start_date, period.end_date)}</span></span>
            <span className="hidden sm:inline mx-2 text-slate-300" aria-hidden="true">|</span>
            <span className="block sm:inline whitespace-nowrap" data-testid="period-transfer">Transfer: <span className="text-slate-700">{formatDate(period.payment_date)}</span></span>
          </span>
          <span className="block" data-testid="period-sync-status">Sinkron terakhir: <span className="text-slate-700">{syncedAt}</span></span>
        </>}>
        <div className="flex w-full sm:w-auto flex-col sm:flex-row sm:flex-wrap xl:flex-nowrap gap-2" data-testid="period-actions">
          {editable && <Btn variant="outline" className="w-full sm:w-auto justify-center whitespace-nowrap" data-testid="fetch-attendance-button" disabled={busy} onClick={requestSync} title="Karyawan & gaji, absensi, klaim lembur, dan Tambahan Bulanan (Transport, Bonus, THR, Potongan Target, Cicilan) terbaru dari ROSY"><DownloadCloud className={`h-4 w-4 ${syncing ? "animate-pulse" : ""}`} /> {syncing ? "Menyinkronkan..." : "Fetch Data Terbaru"}</Btn>}
          {!isManager && editable && <Btn variant="primary" className="w-full sm:w-auto justify-center whitespace-nowrap" data-testid="submit-period-button" disabled={busy || !payslips.length || blocked} title={actionTitle} onClick={() => act("submit", "Draft payroll diajukan ke Manager HRD")}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
          {isManager && pending && <Btn variant="outline" data-testid="reject-period-button" disabled={busy} onClick={() => setRejectOpen(true)} className="w-full sm:w-auto justify-center whitespace-nowrap !border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak Draft</Btn>}
          {isManager && (
            // modal={false}: dialog Batch Payment dibuka dari menu ini; menu modal Radix bisa meninggalkan body tak bisa diklik
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger data-testid="export-bsi-menu" disabled={!payslips.length} className="w-full sm:w-auto justify-center whitespace-nowrap inline-flex items-center gap-1.5 px-4 py-2 min-h-[40px] rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 hover:border-slate-400"><Landmark className="h-4 w-4" /> Export Transfer BSI <ChevronDown className="h-4 w-4" /></DropdownMenuTrigger>
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
          {isManager && <Btn variant="primary" data-testid="approve-all-button" disabled={busy || period.status === "approved" || blocked} onClick={() => setApproveOpen(true)} title={period.status === "approved" ? "Periode sudah dikunci & di-approve" : actionTitle} className="w-full sm:w-auto justify-center whitespace-nowrap"><LockKeyhole className="h-4 w-4" /> Lock & Approve</Btn>}
        </div>
      </PageTitle>

      <div className="mb-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="period-kpis">
        <KpiCard accent="emerald" label="Total Take Home Pay (Net)" value={rp(kpi.thp)} testId="kpi-thp"
          sub={<><span className="num">{payslips.length}</span> karyawan · {payslips.length && approvedCount === payslips.length ? "semua slip terkunci, siap transfer" : <><span className="num">{approvedCount}/{payslips.length}</span> slip terkunci</>}</>} />
        <KpiCard accent="brand" label="Total Bruto (Penghasilan)" value={rp(kpi.gross)} testId="kpi-gross"
          sub={<>Termasuk iuran BPJS perusahaan <span className="num">{rp(kpi.bpjsCo)}</span></>} />
        <KpiCard accent="brand" label={december ? "Total PPh 21 (Desember · Pasal 17)" : "Total PPh 21 (TER Bulanan)"} value={rp(kpi.pph)} testId="kpi-pph21"
          sub={<><span className="num">{taxed}</span> dari <span className="num">{payslips.length}</span> karyawan kena pajak · PP 58/2023</>} />
        <KpiCard accent="brand" label="Total BPJS (Kes + TK)" value={rp(kpi.kes + kpi.tk)} testId="kpi-bpjs"
          sub={<>Kes <span className="num">{rp(kpi.kes)}</span> · TK <span className="num">{rp(kpi.tk)}</span></>} />
      </div>

      {period.last_sync_error && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3 text-sm" data-testid="sync-error-banner">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>Sinkron dari ROSY terakhir gagal: {period.last_sync_error}. Ulangi lewat tombol "Fetch Data Terbaru" di atas — periode belum dapat diajukan sebelum sinkron berhasil.</span>
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
          {(period.submitted_by_name || period.submitted_by) && <>Diajukan oleh <b>{period.submitted_by_name || period.submitted_by}</b>. </>}{isManager ? "Silakan review, lalu Lock & Approve atau Tolak dengan alasan." : "Menunggu keputusan Manager HRD; data tidak dapat diubah."}
        </div>
      )}
      {blocked && (
        <div className="mb-4 overflow-hidden rounded-lg border border-rose-300 bg-rose-50 text-rose-900" data-testid="bank-blocker-banner">
          <div className="flex flex-wrap items-start gap-3 px-4 py-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-rose-200 bg-white text-rose-600"><Landmark className="h-[18px] w-[18px]" /></span>
            {/* lebar minimum: di HP tombol "Lihat ... karyawan" turun ke barisnya sendiri, teks tidak terjepit */}
            <div className="min-w-[15rem] flex-1 text-sm">
              <div className="font-semibold">Payroll belum bisa diproses — rekening <span className="num">{blockers.length}</span> karyawan belum siap dibayar lewat BSI</div>
              <div className="mt-0.5 text-rose-800">Lengkapi <b>No. Rekening</b>, <b>Nama di Rekening</b>, dan <b>Bank (harus BSI)</b> di ROSY HRD → Ubah Karyawan, lalu {editable ? <>klik <b>Fetch Data Terbaru</b> di halaman ini</> : <>klik <b>Sinkron dari ROSY</b> di menu Karyawan</>}. {isManager ? "Tombol Lock & Approve aktif lagi setelah semuanya beres." : "Tombol Ajukan ke Manager aktif lagi setelah semuanya beres."}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {blockerKinds.map(([kind, n]) => <span key={kind} className="inline-flex items-center gap-1 rounded border border-rose-200 bg-white px-2 py-0.5 text-xs font-medium text-rose-800">{kind} <b className="num">{n}</b></span>)}
              </div>
            </div>
            <button type="button" onClick={() => setBankOpen((o) => !o)} aria-expanded={bankOpen} aria-controls="bank-blocker-list" data-testid="bank-blocker-toggle" className="tap inline-flex shrink-0 items-center gap-1 rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-100">
              {bankOpen ? "Tutup daftar" : <>Lihat <span className="num">{blockers.length}</span> karyawan</>} <ChevronDown className={`h-3.5 w-3.5 transition-transform ${bankOpen ? "rotate-180" : ""}`} />
            </button>
          </div>
          {bankOpen && (
            <ul id="bank-blocker-list" className="max-h-80 divide-y divide-rose-100 overflow-y-auto border-t border-rose-200 bg-white text-sm" data-testid="bank-blocker-list">
              {blockers.map((b) => (
                <li key={b.employee_id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 px-4 py-2.5" data-testid="bank-blocker-item">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <Link to={`/hr-manager/payroll/${pid}/employee/${b.employee_id}`} className="tap font-semibold text-slate-900 hover:text-brand-700 hover:underline">{b.name}</Link>
                      <span className="num text-xs text-slate-500">{b.nik}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {b.problems.map((p) => <span key={p.kind} title={p.note} className="inline-flex items-center rounded border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-800">{p.kind}</span>)}
                    </div>
                  </div>
                  <div className="text-left sm:text-right text-xs text-slate-500">
                    <div>{b.bank || <span className="text-rose-700">bank kosong</span>} · {b.account_number ? <span className="num">{b.account_number}</span> : <span className="text-rose-700">no. rekening kosong</span>}</div>
                    <div>{b.account_name ? <>a.n. {b.account_name}</> : <span className="text-rose-700">nama di rekening kosong</span>}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {/* panel "Perhatian & Anomali" dihapus (user 15 Okt 2026: "sudah ada filternya di bawah"); peringatan yang tidak punya
          filter tetap tampil sebagai banner seperti semula, hanya bila ada kasusnya */}
      {!period.attendance_synced_at && <div className="mb-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5" data-testid="sync-attendance-pending">Absensi belum diambil — klik "Fetch Data Terbaru".</div>}
      {noSignature && period.status !== "approved" && (
        <div className="mb-4 flex items-center gap-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5 text-sm" data-testid="signer-missing-banner">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Belum ada penandatangan slip — slip yang di-approve akan terbit <b>tanpa nama penandatangan</b> (QR verifikasi tetap tercetak). Cek di Konfigurasi → Penandatangan Slip Gaji.</span>
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
          <Smartphone className="h-4 w-4 text-brand-600" />
          <span>Slip PDF ke aplikasi Rumatku: <b className="num" data-testid="delivery-sent-count">{sentCount}/{payslips.length}</b> terkirim{sending && " · sedang mengirim..."}{failed > 0 && <> · <b data-testid="delivery-failed-count">{failed}</b> gagal setelah 3x percobaan otomatis</>}</span>
          {failed > 0 && isManager && <Btn variant="outline" data-testid="resend-failed-button" disabled={busy || sending} onClick={() => act("resend-failed", "Slip gagal dikirim ulang ke Rumatku")} className="ml-auto"><RotateCw className="h-4 w-4" /> Kirim Ulang Semua yang Gagal</Btn>}
        </div>
      )}

      <div id="payslip-review" className="scroll-mt-20">
        <Panel>
          <div className="px-4 sm:px-5 pt-4 pb-3 border-b border-slate-200" data-testid="payslip-toolbar">
            <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-bold text-slate-900">Daftar Review Rincian Penggajian Karyawan</h2>
                <p className="mt-0.5 text-xs text-slate-500" data-testid="payslip-basis">Basis <span className="num">{wd}</span> hari kerja · Potongan presensi/absensi <span className="num">1/{wd}</span> per poin/hari · PPh 21 TER PP 58/2023, dasar {kotor ? "kotor (sebelum potongan presensi & absensi)" : "bersih (sesudah potongan presensi & absensi)"}</p>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                {/* bilah cari diberi ruang napas (user 12 Okt 2026); kini juga mencari NIK */}
                <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-2 bg-white w-full sm:w-64 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-700/10">
                  <Search className="h-4 w-4 text-slate-400" />
                  <input data-testid="payslip-search-input" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Cari NIK / Nama..." className="outline-none text-sm w-full bg-transparent" />
                </label>
                <select data-testid="payslip-dept-select" value={dept} onChange={(e) => { setDept(e.target.value); setPage(1); }} className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white text-slate-700">
                  <option value="">Semua Departemen</option>
                  {depts.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
              </div>
            </div>
            {/* tab penyaring = kartu Ikut Digaji / Lembur / Unpaid / Cuti Melahirkan / Tidak Penuh / Rekening (10 & 14 Okt 2026) */}
            <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="period-summary">
              {tabs.map(([key, label, count, testId, danger]) => {
                const names = key ? namesOf(summary?.[key] || []) : [];
                return (
                  <FilterTab key={label} label={label} count={count} on={activeFilter === key} alarm={danger ? "rose" : undefined} testId={testId}
                    disabled={!!key && !count} onClick={() => applyFilter(activeFilter === key ? null : key)}
                    title={names.length ? `${names.slice(0, 40).join(", ")}${names.length > 40 ? `, dan ${names.length - 40} lainnya` : ""}` : ""} />
                );
              })}
            </div>
            {activeFilter && (
              <div className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-slate-600" data-testid="payslip-filter">
                <span>Filter: <b className="text-slate-900">{FILTER_LABELS[activeFilter]}</b> · <span className="num">{only.size}</span> karyawan{filterHint && <> · {filterHint}</>}</span>
                <button type="button" onClick={() => applyFilter(null)} className="tap inline-flex items-center gap-1 font-semibold text-brand-700 hover:text-rose-600" data-testid="payslip-filter-clear"><XCircle className="h-3.5 w-3.5" /> Hapus filter</button>
              </div>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="payslips-table">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  {COLS.map((h, i) => (
                    <th key={h} className={`px-3 py-3 font-semibold align-bottom ${i === 0 ? `text-left ${STICKY} bg-slate-50` : i === COLS.length - 1 ? "text-center" : "text-right"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pageRows.map((s) => {
                  const nik = s.employee.nik;
                  const blocker = blockerById[s.employee_id];
                  const link = `/hr-manager/payroll/${pid}/employee/${s.employee_id}`;
                  return (
                    <tr key={s.id} className="group hover:bg-slate-50" data-testid={`payslip-row-${nik}`}>
                      <td className={`px-3 py-2.5 min-w-[11rem] bg-white group-hover:bg-slate-50 ${STICKY}`}>
                        <div className="font-semibold leading-snug">
                          <Link to={link} className="tap text-slate-900 hover:text-brand-700 hover:underline">{s.employee.name}</Link>
                          {s.is_manually_adjusted && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-700">EDIT</span>}
                          {blocker && <span title={blocker.problems.map((p) => `${p.kind}: ${p.note}`).join("\n")} className="ml-2 rounded bg-rose-100 px-1.5 py-0.5 text-xs font-semibold text-rose-700" data-testid={`bank-badge-${nik}`}>REKENING</span>}
                        </div>
                        <div className="num text-xs text-slate-500 whitespace-nowrap">{nik} · {s.ptkp_status}</div>
                      </td>
                      <RpCell v={s.gross_earnings} tone={MONEY[0][1]} />
                      <RpCell v={s.taxable_gross} tone={MONEY[1][1]} />
                      <RpCell v={s.pph21_amount} tone={MONEY[2][1]} />
                      <td className={`px-3 py-3 num text-right ${s.late_penalty_points ? "font-semibold text-rose-600" : "text-slate-400"}`} data-testid={`poin-presensi-${nik}`}>{s.late_penalty_points || 0}</td>
                      <td className={`px-3 py-3 num text-right ${s.absence_points ? "font-semibold text-rose-600" : "text-slate-400"}`} data-testid={`poin-absensi-${nik}`}>{s.absence_points ?? 0}</td>
                      <RpCell v={s.total_deductions} tone={MONEY[5][1]} />
                      <RpCell v={s.iuran_bpjs_kes_total} tone={MONEY[6][1]} />
                      <RpCell v={s.iuran_bpjs_tk_total} tone={MONEY[7][1]} />
                      <td className="px-3 py-2.5 text-center">
                        <Link to={link} data-testid={`review-${nik}`} className="tap font-semibold text-brand-700 hover:underline whitespace-nowrap">Review</Link>
                      </td>
                    </tr>
                  );
                })}
                {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{payslips.length ? "Tidak ada karyawan yang cocok." : "Belum ada slip. Klik \"Fetch Data Terbaru\"."}</td></tr>}
              </tbody>
              {!!rows.length && (
                // total seluruh hasil saring (semua halaman), di bawah kolom rupiahnya masing-masing; angkanya 12 px supaya
                // jumlah miliaran tidak memaksa kolom melebar
                <tfoot className="bg-slate-50 font-semibold border-t-2 border-slate-200">
                  <tr>
                    <td className={`px-3 py-3 text-xs uppercase tracking-wider text-slate-500 whitespace-nowrap bg-slate-50 ${STICKY}`}>Total <span className="num">{rows.length}</span> karyawan</td>
                    {MONEY.map((m, i) => (m
                      ? <td key={m[0]} className="px-3 py-3 num text-xs text-right whitespace-nowrap text-slate-900" data-testid={`total-${m[0]}`}>{rp(rows.reduce((a, s) => a + (s[m[0]] || 0), 0))}</td>
                      : <td key={`poin-${i}`} />))}
                    <td />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          {!!rows.length && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 sm:px-5 py-3 border-t border-slate-200 text-sm text-slate-600" data-testid="payslip-pagination">
              <div>Menampilkan <b className="num">{perPage ? (cur - 1) * perPage + 1 : 1}</b>–<b className="num">{perPage ? Math.min(cur * perPage, rows.length) : rows.length}</b> dari <b className="num">{rows.length}</b> karyawan</div>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-slate-500">Baris per halaman
                  <select data-testid="payslip-per-page" value={perPage} onChange={(e) => {
                    const n = Number(e.target.value);
                    setPerPage(n);
                    setPage(1);
                    try { localStorage.setItem(PER_PAGE_KEY, String(n)); } catch { /* tanpa penyimpanan: tetap jalan */ }
                  }} className="border border-slate-300 rounded-md px-2 py-1 text-sm bg-white text-slate-700">
                    {PER_PAGE.map((n) => <option key={n} value={n}>{n || "Semua"}</option>)}
                  </select>
                </label>
                {pageCount > 1 && (
                  <nav className="flex items-center gap-1" aria-label="Halaman tabel">
                    <PageBtn disabled={cur === 1} onClick={() => goPage(cur - 1)} aria-label="Halaman sebelumnya"><ChevronLeft className="h-4 w-4" /></PageBtn>
                    {pageItems(cur, pageCount).map((p) => (typeof p === "string"
                      ? <span key={p} className="px-1 text-slate-400">…</span>
                      : <PageBtn key={p} active={p === cur} aria-current={p === cur ? "page" : undefined} onClick={() => goPage(p)} data-testid={`payslip-page-${p}`}><span className="num">{p}</span></PageBtn>))}
                    <PageBtn disabled={cur === pageCount} onClick={() => goPage(cur + 1)} aria-label="Halaman berikutnya"><ChevronRight className="h-4 w-4" /></PageBtn>
                  </nav>
                )}
              </div>
            </div>
          )}
        </Panel>
      </div>
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
            <DialogDescription><span className="num">{payslips.length}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(kpi.thp)}</b></DialogDescription>
          </DialogHeader>
          <div className="text-sm text-slate-600 space-y-2">
            {editable && <p className="bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2" data-testid="approve-direct-note">Periode ini belum diajukan Supervisor HRD — Anda meng-approve langsung dari draft.</p>}
            {noSignature && <p className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-3 py-2" data-testid="approve-no-signature-note">Penandatangan belum ada — slip PDF akan terbit <b>tanpa nama penandatangan</b> (QR verifikasi tetap tercetak).</p>}
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
            <DialogDescription>Periode <b>{period.period_name}</b> · <span className="num">{payslips.length}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(kpi.thp)}</b></DialogDescription>
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
