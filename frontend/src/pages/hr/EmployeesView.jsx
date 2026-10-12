import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, Users, UserX, AlertTriangle, UserMinus, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS, DATA_ISSUE_LABELS, periodNameFor, formatDateTime, timeAgo } from "@/lib/format";
import { PageTitle, Panel, SummaryCard } from "@/components/common";

// kolom "Sinkron" per baris dibuang (user 12 Okt 2026): semua baris tersinkron bersamaan, waktunya cukup di judul
const COLS = ["NIK", "Nama", "Dept", "L/P", "PTKP", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam", "BPJS", "Rekening"];
const BPJS_LABELS = { kes: "Kes", jkk: "JKK", jkm: "JKM", jht: "JHT", jp: "JP" };

const bpjsText = (e) => {
  if (e.bpjs_programs) return Object.keys(BPJS_LABELS).filter((p) => e.bpjs_programs[p]).map((p) => BPJS_LABELS[p]).join(" + ") || "-";
  return [e.has_bpjs_kes !== false && "Kes", e.has_bpjs_tk !== false && "TK"].filter(Boolean).join(" + ") || "-";
};

// kartu ringkasan menggantikan paragraf status sinkron (user 12 Okt 2026): satu angka per hal yang perlu diketahui
// HRD, sekaligus penyaring tabel; yang bukan bawaan tampil sebagai filter yang bisa dihapus
const inRosy = (e) => e.in_rosy !== false;
const FILTERS = {
  paid: { label: "Ikut Digaji", match: inRosy },
  issues: { label: "Data Perlu Dirapikan", match: (e) => inRosy(e) && e.data_issues?.length > 0 },
  gone: { label: "Tidak Lagi di ROSY", match: (e) => !inRosy(e) },
};
const STALE_MS = 7 * 86400000;

export default function EmployeesView() {
  const [list, setList] = useState([]);
  const [status, setStatus] = useState({});
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("paid");
  const [showSkipped, setShowSkipped] = useState(false);
  useEffect(() => {
    api.get("/hr/employees").then((r) => setList(r.data));
    api.get("/hr/employees/sync-status").then((r) => setStatus(r.data || {}));
  }, []);

  const count = (key) => list.filter(FILTERS[key].match).length;
  const toggle = (key) => setFilter(filter === key ? "paid" : key);
  const rows = list.filter((e) => FILTERS[filter].match(e) && `${e.nik} ${e.name} ${e.department}`.toLowerCase().includes(q.trim().toLowerCase()));
  const skipped = [...(status.skipped || [])].sort((a, b) => `${a.alasan}${a.name}`.localeCompare(`${b.alasan}${b.name}`));
  // jumlah per jenis masalah; seorang karyawan bisa punya lebih dari satu, jadi totalnya bisa melebihi angka kartu
  const issueTypes = Object.entries(status.data_issues || {}).sort((a, b) => b[1] - a[1]);
  const issueText = issueTypes.map(([k, n]) => `${DATA_ISSUE_LABELS[k] || k} ${n}`).join(" · ");
  const issueTop = issueTypes.length ? `${issueTypes.length > 1 ? "terbanyak: " : ""}${DATA_ISSUE_LABELS[issueTypes[0][0]] || issueTypes[0][0]} ${issueTypes[0][1]}` : "";
  const month = status.periode ? periodNameFor(`${status.periode}-01`, `${status.periode}-01`) : null;
  const stale = status.synced_at && Date.now() - new Date(status.synced_at) > STALE_MS;

  return (
    <div>
      <PageTitle title="Data Karyawan & Gaji" subtitle={status.synced_at ? (
        <span data-testid="employee-sync-status">
          Hanya-lihat, dari ROSY{month && ` · gaji ${month}`} · <span className={stale ? "text-amber-700 font-medium" : ""}>diperbarui {formatDateTime(status.synced_at)} ({timeAgo(status.synced_at)})</span>
          {" · "}<Link to="/hr-manager" className="tap text-blue-900 hover:underline">perbarui lewat Sinkron dari ROSY di Dashboard</Link>
        </span>
      ) : "Hanya-lihat, dari ROSY · belum pernah disinkron — jalankan Sinkron dari ROSY di Dashboard"}>
        <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-1.5 bg-white w-64">
          <Search className="h-4 w-4 text-slate-400" />
          <input data-testid="employee-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full" />
        </label>
      </PageTitle>
      {list.length > 0 && (
        <div className="mb-4 grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="employee-summary">
          <SummaryCard icon={Users} label="Ikut Digaji" value={count("paid")} sub="punya Kontrak Gaji di ROSY" active={filter === "paid"} onClick={() => setFilter("paid")} testId="emp-sum-paid" />
          <SummaryCard icon={UserX} label="Tidak Ikut Digaji" value={skipped.length} warn sub={skipped.length ? "klik untuk lihat nama & alasannya" : "semua ikut digaji"}
            active={showSkipped} onClick={skipped.length ? () => setShowSkipped(!showSkipped) : undefined} testId="emp-sum-skipped" />
          <SummaryCard icon={AlertTriangle} label="Data Perlu Dirapikan" value={count("issues")} warn sub={issueTop || "data lengkap"}
            active={filter === "issues"} onClick={count("issues") ? () => toggle("issues") : undefined} testId="emp-sum-issues" />
          <SummaryCard icon={UserMinus} label="Tidak Lagi di ROSY" value={count("gone")} names={list.filter(FILTERS.gone.match).map((e) => e.name)} sub="keluar atau dihapus di ROSY"
            active={filter === "gone"} onClick={count("gone") ? () => toggle("gone") : undefined} testId="emp-sum-gone" />
        </div>
      )}
      {showSkipped && skipped.length > 0 && (
        <Panel title={`Tidak ikut digaji · ${skipped.length} karyawan`} className="mb-4"
          right={<button type="button" onClick={() => setShowSkipped(false)} className="tap text-slate-400 hover:text-slate-700" title="Tutup"><XCircle className="h-4 w-4" /></button>}>
          <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto" data-testid="employee-skipped-list">
            {skipped.map((s) => (
              <div key={s.employee_id || s.nik} className="flex items-center justify-between gap-4 px-5 py-2 text-sm">
                <span><span className="font-medium text-slate-800">{s.name}</span> <span className="num text-xs text-slate-400">{s.nik}</span></span>
                <span className="text-xs text-slate-500 text-right">{s.alasan}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}
      <Panel>
        {filter !== "paid" && (
          <div className="px-5 py-3 border-b border-slate-200 flex flex-wrap items-center gap-3 text-sm" data-testid="employee-filter">
            <span className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-3 py-1.5">
              Filter: <b>{FILTERS[filter].label}</b> · <span className="num">{rows.length}</span> karyawan
              <button type="button" onClick={() => setFilter("paid")} className="tap text-blue-900 hover:text-rose-600" title="Hapus filter" data-testid="employee-filter-clear"><XCircle className="h-4 w-4" /></button>
            </span>
            {filter === "issues" && <span className="text-xs text-slate-500">Rincian: {issueText} — dirapikan di ROSY, tidak menghalangi payroll</span>}
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
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{list.length ? "Tidak ada yang cocok." : "Belum ada data — jalankan \"Sinkron dari ROSY\" di Dashboard."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
