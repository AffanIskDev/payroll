import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS, DATA_ISSUE_LABELS, periodNameFor, formatDateTime, timeAgo } from "@/lib/format";
import { PageTitle, Panel, Chip, FilterTab } from "@/components/common";

// kolom "Sinkron" per baris dibuang (user 12 Okt 2026): semua baris tersinkron bersamaan, waktunya cukup di judul.
// 15 Okt 2026 tampilan diselaraskan dengan halaman periode (rupiah rata kanan, angka 0 pudar, status payroll bertitik warna,
// program BPJS jadi label; warna mengikuti desain RUMAT), lalu kolomnya dirapikan atas permintaan user: "kolom karyawan ada nama, nik, jenis kelamin,
// setelah itu kolom dept, setelah itu status ptkp baru gaji dst" — NIK & L/P masuk kolom Karyawan (email tetap di bawahnya)
const COLS = ["Karyawan", "Dept", "Status PTKP", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam", "BPJS", "Rekening"];
const RIGHT = new Set(["Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam"]);
const GENDER = { L: "Laki-laki", P: "Perempuan" };
// kolom Karyawan menempel di kiri saat tabel digeser; garis tipis memisahkannya dari kolom lain
const STICKY = "sticky left-0 z-10 shadow-[1px_0_0_#e2e8f0]";
const BPJS_LABELS = { kes: "Kes", jkk: "JKK", jkm: "JKM", jht: "JHT", jp: "JP" };

const bpjsList = (e) => {
  if (e.bpjs_programs) return Object.keys(BPJS_LABELS).filter((p) => e.bpjs_programs[p]).map((p) => BPJS_LABELS[p]);
  return [e.has_bpjs_kes !== false && "Kes", e.has_bpjs_tk !== false && "TK"].filter(Boolean);
};

// warna teks + titik per status payroll (label tanpa kotak, sama dengan label status lain sejak 13 Okt 2026); hanya warna bermakna
const PAYROLL_STATUS_TONE = {
  active: ["text-emerald-700", "bg-emerald-500"],
  unpaid_leave: ["text-amber-700", "bg-amber-500"],
  prolonged_illness: ["text-amber-700", "bg-amber-500"],
  work_accident_stmb: ["text-rose-700", "bg-rose-500"],
};

// angka 0 dipudarkan supaya yang berisi menonjol
const RpCell = ({ v, tone, testId }) => (
  <td className={`px-2.5 py-2.5 num text-right whitespace-nowrap ${v ? tone : "text-slate-400"}`} data-testid={testId}>{rp(v)}</td>
);

// Kartu ringkasan dibuang (user 13 Okt 2026), diganti satu penyaring "data belum lengkap" (NPWP, tgl lahir, rekening, dll —
// hasil periksa ROSY, sama dengan "Perlu Ditinjau" di Dashboard). Tabel hanya memuat karyawan yang masih ada di ROSY.
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
  const sep = <>{" "}<span className="hidden sm:inline mx-1.5 text-slate-300" aria-hidden="true">|</span>{" "}</>;

  return (
    <div>
      <PageTitle title="Data Karyawan & Gaji" titleExtra={<Chip tone="slate" title="Diubah di ROSY HRD, bukan di RASA">Hanya-lihat · dari ROSY</Chip>}
        subtitle={status.synced_at ? (
          <span data-testid="employee-sync-status">
            {month && <><span className="block sm:inline whitespace-nowrap">Gaji: <span className="text-slate-700">{month}</span></span>{sep}</>}
            <span className="block sm:inline whitespace-nowrap">Diperbarui: <span className={stale ? "font-medium text-amber-700" : "text-slate-700"}>{formatDateTime(status.synced_at)} ({timeAgo(status.synced_at)})</span></span>
            {sep}
            <Link to="/hr-manager/payroll" className="tap block sm:inline font-medium text-brand-700 hover:underline">Perbarui lewat Fetch Data Terbaru di halaman periode (menu Payroll)</Link>
          </span>
        ) : "Belum pernah disinkron — jalankan Fetch Data Terbaru di halaman periode (menu Payroll)"} />
      <Panel>
        <div className="px-4 sm:px-5 pt-4 pb-3 border-b border-slate-200" data-testid="employee-toolbar">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-bold text-slate-900">Daftar Karyawan & Komponen Gaji</h2>
              <p className="mt-0.5 text-xs text-slate-500">Karyawan yang masih ada di ROSY · gaji pokok, tunjangan, tarif lembur, program BPJS, dan rekening dari sinkron terakhir</p>
            </div>
            <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-2 bg-white w-full sm:w-64 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-700/10">
              <Search className="h-4 w-4 text-slate-400" />
              <input data-testid="employee-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full bg-transparent" />
            </label>
          </div>
          {/* lencana "N karyawan data belum lengkap" (13 Okt 2026) kini tab penyaring seperti di halaman periode */}
          <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="employee-tabs">
            <FilterTab label="Semua" count={current.length} on={!onlyIncomplete} onClick={() => setOnlyIncomplete(false)} testId="employee-tab-all" />
            <FilterTab label="Data Belum Lengkap" count={lacking.length} on={onlyIncomplete} alarm="amber" disabled={!lacking.length} onClick={() => setOnlyIncomplete(!onlyIncomplete)} testId="employee-issues-badge"
              title={`${issueText ? `${issueText} — ` : ""}klik untuk ${onlyIncomplete ? "menampilkan semua karyawan" : "menampilkan hanya yang datanya belum lengkap"}`} />
          </div>
          {onlyIncomplete && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-slate-600" data-testid="employee-filter">
              <span>Filter: <b className="text-slate-900">Data Belum Lengkap</b> · <span className="num">{rows.length}</span> karyawan{issueText && <> · Rincian: {issueText} — dirapikan di ROSY, tidak menghalangi payroll</>}</span>
              <button type="button" onClick={() => setOnlyIncomplete(false)} className="tap inline-flex items-center gap-1 font-semibold text-brand-700 hover:text-rose-600" title="Hapus filter" data-testid="employee-filter-clear"><XCircle className="h-3.5 w-3.5" /> Hapus filter</button>
            </div>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]" data-testid="employees-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                {COLS.map((h, i) => (
                  <th key={h} className={`px-2.5 py-3 font-semibold align-bottom ${RIGHT.has(h) ? "text-right" : "text-left"} ${i === 0 ? `${STICKY} bg-slate-50` : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((e) => {
                const [tone, dot] = PAYROLL_STATUS_TONE[e.payroll_status] || ["text-slate-600", "bg-slate-400"];
                const bpjs = bpjsList(e);
                return (
                  <tr key={e.id} className={`group hover:bg-slate-50 ${inRosy(e) ? "" : "opacity-60"}`} data-testid={`employee-row-${e.nik}`}>
                    <td className={`px-2.5 py-2.5 min-w-[11rem] max-w-[15rem] bg-white group-hover:bg-slate-50 ${STICKY}`}>
                      <div className="font-semibold leading-snug text-slate-900">
                        {e.name}
                        {!inRosy(e) && <span className="ml-2 whitespace-nowrap rounded bg-slate-200 px-1.5 py-0.5 text-xs font-semibold text-slate-600">tidak ada di ROSY</span>}
                        {e.data_issues?.length > 0 && <span title={e.data_issues.map((i) => DATA_ISSUE_LABELS[i] || i).join(", ")} className="ml-2 whitespace-nowrap rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-700" data-testid={`employee-issues-${e.nik}`}>⚠ {e.data_issues.length}</span>}
                      </div>
                      <div className="text-xs text-slate-500"><span className="num">{e.nik}</span>{e.gender && <> · {GENDER[e.gender] || e.gender}</>}</div>
                      {e.email && <div className="text-xs text-slate-400 break-all">{e.email}</div>}
                    </td>
                    <td className="px-2.5 py-2.5 text-slate-700">{e.department}{e.position && <div className="text-xs text-slate-500">{e.position}</div>}</td>
                    <td className="px-2.5 py-2.5 num text-slate-700 whitespace-nowrap">{e.ptkp_status || `${e.marital_status}/${e.dependents_count}`}{e.has_husband_certificate ? " ✓SK" : ""}</td>
                    <td className="px-2.5 py-2.5 text-xs">
                      <span className={`inline-flex items-start gap-1.5 font-medium ${tone}`}><span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden="true" />{PAYROLL_STATUS_LABELS[e.payroll_status] || e.payroll_status}</span>
                    </td>
                    <RpCell v={e.basic_salary} tone="text-slate-900 font-semibold" />
                    <RpCell v={e.position_allowance} tone="text-slate-900" />
                    <RpCell v={e.monthly_attendance_allowance} tone="text-slate-900" />
                    <RpCell v={e.overtime_hourly_rate} tone="text-slate-900" testId={`employee-ot-rate-${e.nik}`} />
                    <td className="px-2.5 py-2.5">
                      {bpjs.length ? (
                        <div className="grid w-[7.25rem] grid-cols-3 gap-1">
                          {bpjs.map((b) => <span key={b} className="rounded border border-slate-200 bg-slate-50 py-0.5 text-center text-xs font-semibold text-slate-600">{b}</span>)}
                        </div>
                      ) : <span className="text-slate-400">-</span>}
                    </td>
                    <td className="px-2.5 py-2.5 text-xs whitespace-nowrap">
                      <div className="font-medium text-slate-700">{e.bank_name}</div>
                      <div className="num text-slate-500">{e.bank_account_number}</div>
                    </td>
                  </tr>
                );
              })}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{list.length ? "Tidak ada yang cocok." : "Belum ada data — jalankan \"Fetch Data Terbaru\" di halaman periode (menu Payroll)."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
