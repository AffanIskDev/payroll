import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, AlertTriangle, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS, DATA_ISSUE_LABELS, periodNameFor, formatDateTime, timeAgo } from "@/lib/format";
import { PageTitle, Panel } from "@/components/common";

// kolom "Sinkron" per baris dibuang (user 12 Okt 2026): semua baris tersinkron bersamaan, waktunya cukup di judul
const COLS = ["NIK", "Nama", "Dept", "L/P", "PTKP", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam", "BPJS", "Rekening"];
const BPJS_LABELS = { kes: "Kes", jkk: "JKK", jkm: "JKM", jht: "JHT", jp: "JP" };

const bpjsText = (e) => {
  if (e.bpjs_programs) return Object.keys(BPJS_LABELS).filter((p) => e.bpjs_programs[p]).map((p) => BPJS_LABELS[p]).join(" + ") || "-";
  return [e.has_bpjs_kes !== false && "Kes", e.has_bpjs_tk !== false && "TK"].filter(Boolean).join(" + ") || "-";
};

// Kartu ringkasan dibuang (user 13 Okt 2026), diganti satu lencana peringatan bila ada karyawan yang datanya belum
// lengkap (NPWP, tgl lahir, rekening, dll — hasil periksa ROSY, sama dengan "Perlu Ditinjau" di Dashboard). Tabel hanya
// memuat karyawan yang masih ada di ROSY; lencananya sekaligus menyaring tabel.
const inRosy = (e) => e.in_rosy !== false;
const incomplete = (e) => e.data_issues?.length > 0;
const STALE_MS = 7 * 86400000;

export default function EmployeesView() {
  const [list, setList] = useState([]);
  const [status, setStatus] = useState({});
  const [q, setQ] = useState("");
  const [onlyIncomplete, setOnlyIncomplete] = useState(false);
  useEffect(() => {
    api.get("/hr/employees").then((r) => setList(r.data));
    api.get("/hr/employees/sync-status").then((r) => setStatus(r.data || {}));
  }, []);

  const current = list.filter(inRosy);
  const lacking = current.filter(incomplete);
  const rows = (onlyIncomplete ? lacking : current).filter((e) => `${e.nik} ${e.name} ${e.department}`.toLowerCase().includes(q.trim().toLowerCase()));
  // jumlah per jenis masalah; seorang karyawan bisa punya lebih dari satu, jadi totalnya bisa melebihi jumlah karyawan
  const issueTypes = Object.entries(status.data_issues || {}).sort((a, b) => b[1] - a[1]);
  const issueText = issueTypes.map(([k, n]) => `${DATA_ISSUE_LABELS[k] || k} ${n}`).join(" · ");
  const month = status.periode ? periodNameFor(`${status.periode}-01`, `${status.periode}-01`) : null;
  const stale = status.synced_at && Date.now() - new Date(status.synced_at) > STALE_MS;

  return (
    <div>
      <PageTitle title="Data Karyawan & Gaji" subtitle={status.synced_at ? (
        <span data-testid="employee-sync-status">
          Hanya-lihat, dari ROSY{month && ` · gaji ${month}`} · <span className={stale ? "text-amber-700 font-medium" : ""}>diperbarui {formatDateTime(status.synced_at)} ({timeAgo(status.synced_at)})</span>
          {" · "}<Link to="/hr-manager/payroll" className="tap text-blue-900 hover:underline">perbarui lewat Fetch Data Terbaru di halaman periode (menu Payroll)</Link>
        </span>
      ) : "Hanya-lihat, dari ROSY · belum pernah disinkron — jalankan Fetch Data Terbaru di halaman periode (menu Payroll)"}>
        {lacking.length > 0 && (
          <button type="button" onClick={() => setOnlyIncomplete(!onlyIncomplete)} aria-pressed={onlyIncomplete} data-testid="employee-issues-badge"
            title={`${issueText ? `${issueText} — ` : ""}klik untuk ${onlyIncomplete ? "menampilkan semua karyawan" : "menampilkan hanya yang datanya belum lengkap"}`}
            className={`tap inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors ${onlyIncomplete ? "bg-amber-200 border-amber-400 text-amber-900" : "bg-amber-50 border-amber-300 text-amber-800 hover:bg-amber-100"}`}>
            <AlertTriangle className="h-4 w-4" /> <span className="num">{lacking.length}</span> karyawan data belum lengkap
          </button>
        )}
        <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-1.5 bg-white w-64">
          <Search className="h-4 w-4 text-slate-400" />
          <input data-testid="employee-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full" />
        </label>
      </PageTitle>
      <Panel>
        {onlyIncomplete && (
          <div className="px-5 py-3 border-b border-slate-200 flex flex-wrap items-center gap-3 text-sm" data-testid="employee-filter">
            <span className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-3 py-1.5">
              Filter: <b>Data Belum Lengkap</b> · <span className="num">{rows.length}</span> karyawan
              <button type="button" onClick={() => setOnlyIncomplete(false)} className="tap text-blue-900 hover:text-rose-600" title="Hapus filter" data-testid="employee-filter-clear"><XCircle className="h-4 w-4" /></button>
            </span>
            {issueText && <span className="text-xs text-slate-500">Rincian: {issueText} — dirapikan di ROSY, tidak menghalangi payroll</span>}
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="employees-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{COLS.map((h) => <th key={h} className="text-left px-4 py-3 whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((e) => (
                <tr key={e.id} className={`hover:bg-slate-50 ${inRosy(e) ? "" : "opacity-60"}`} data-testid={`employee-row-${e.nik}`}>
                  <td className="px-4 py-3 num">{e.nik}</td>
                  <td className="px-4 py-3 font-semibold whitespace-nowrap">
                    {e.name}
                    {!inRosy(e) && <span className="ml-2 text-[11px] text-slate-600 bg-slate-200 px-1.5 py-0.5 rounded">tidak ada di ROSY</span>}
                    {e.data_issues?.length > 0 && <span title={e.data_issues.map((i) => DATA_ISSUE_LABELS[i] || i).join(", ")} className="ml-2 text-[11px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded" data-testid={`employee-issues-${e.nik}`}>⚠ {e.data_issues.length}</span>}
                    <div className="text-xs font-normal text-slate-500">{e.email}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{e.department}{e.position && <div className="text-xs text-slate-500">{e.position}</div>}</td>
                  <td className="px-4 py-3">{e.gender}</td>
                  <td className="px-4 py-3 num">{e.ptkp_status || `${e.marital_status}/${e.dependents_count}`}{e.has_husband_certificate ? " ✓SK" : ""}</td>
                  <td className="px-4 py-3 text-xs">{PAYROLL_STATUS_LABELS[e.payroll_status] || e.payroll_status}</td>
                  <td className="px-4 py-3 num whitespace-nowrap">{rp(e.basic_salary)}</td>
                  <td className="px-4 py-3 num whitespace-nowrap">{rp(e.position_allowance)}</td>
                  <td className="px-4 py-3 num whitespace-nowrap">{rp(e.monthly_attendance_allowance)}</td>
                  <td className="px-4 py-3 num whitespace-nowrap" data-testid={`employee-ot-rate-${e.nik}`}>{rp(e.overtime_hourly_rate)}</td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap">{bpjsText(e)}</td>
                  <td className="px-4 py-3 num text-xs whitespace-nowrap">{e.bank_name} {e.bank_account_number}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{list.length ? "Tidak ada yang cocok." : "Belum ada data — jalankan \"Fetch Data Terbaru\" di halaman periode (menu Payroll)."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
