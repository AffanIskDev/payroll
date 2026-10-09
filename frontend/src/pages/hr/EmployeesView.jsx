import { useCallback, useEffect, useState } from "react";
import { Search, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS, DATA_ISSUE_LABELS } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";

const COLS = ["NIK", "Nama", "Dept", "L/P", "PTKP", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam", "BPJS", "Rekening", "Sinkron"];
const BPJS_LABELS = { kes: "Kes", jkk: "JKK", jkm: "JKM", jht: "JHT", jp: "JP" };

const bpjsText = (e) => {
  if (e.bpjs_programs) return Object.keys(BPJS_LABELS).filter((p) => e.bpjs_programs[p]).map((p) => BPJS_LABELS[p]).join(" + ") || "-";
  return [e.has_bpjs_kes !== false && "Kes", e.has_bpjs_tk !== false && "TK"].filter(Boolean).join(" + ") || "-";
};

export default function EmployeesView() {
  const [list, setList] = useState([]);
  const [status, setStatus] = useState({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => Promise.all([
    api.get("/hr/employees").then((r) => setList(r.data)),
    api.get("/hr/employees/sync-status").then((r) => setStatus(r.data || {})),
  ]), []);
  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setBusy(true);
    try {
      const r = await api.post("/hr/employees/sync");
      toast.success(`${r.data.count} karyawan tersinkron dari ROSY (periode ${r.data.periode})`);
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const rows = list.filter((e) => `${e.nik} ${e.name} ${e.department}`.toLowerCase().includes(q.toLowerCase()));
  const skipped = status.skipped || [];
  const issues = Object.entries(status.data_issues || {});

  return (
    <div>
      <PageTitle title="Data Karyawan & Gaji" subtitle="Hanya-lihat. Sumber data: ROSY (HAM) — sinkron lewat tombol, dan otomatis saat membuat periode payroll baru">
        <Btn variant="outline" data-testid="sync-employees-button" disabled={busy} onClick={sync}><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> {busy ? "Menyinkron..." : "Sinkron dari ROSY"}</Btn>
        <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-1.5 bg-white w-64">
          <Search className="h-4 w-4 text-slate-400" />
          <input data-testid="employee-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full" />
        </label>
      </PageTitle>
      {status.synced_at && (
        <div className="mb-4 bg-white border border-slate-200 rounded-md px-4 py-2.5 text-sm space-y-1" data-testid="employee-sync-status">
          <div>
            Sinkron terakhir <b className="num">{new Date(status.synced_at).toLocaleString("id-ID")}</b> · periode <span className="num">{status.periode}</span> · <b className="num">{status.count}</b> karyawan
            {status.company ? ` · ${status.company.nama_legal || status.company.nama}` : ""}
            {status.not_in_rosy > 0 && <> · <b className="num">{status.not_in_rosy}</b> tidak lagi ada di ROSY</>}
          </div>
          {skipped.length > 0 && (
            <div className="text-amber-800" data-testid="employee-sync-skipped">
              Tidak ikut ({skipped.length}): {skipped.slice(0, 8).map((s) => `${s.name} — ${s.alasan}`).join("; ")}{skipped.length > 8 ? `; dan ${skipped.length - 8} lainnya` : ""}
            </div>
          )}
          {issues.length > 0 && (
            <div className="text-amber-800" data-testid="employee-sync-issues">
              Data ROSY yang perlu dirapikan HRD: {issues.map(([k, n]) => `${DATA_ISSUE_LABELS[k] || k} ${n}`).join(" · ")}
            </div>
          )}
        </div>
      )}
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="employees-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{COLS.map((h) => <th key={h} className="text-left px-4 py-3 whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((e) => (
                <tr key={e.id} className={`hover:bg-slate-50 ${e.in_rosy === false ? "opacity-60" : ""}`} data-testid={`employee-row-${e.nik}`}>
                  <td className="px-4 py-3 num">{e.nik}</td>
                  <td className="px-4 py-3 font-semibold whitespace-nowrap">
                    {e.name}
                    {e.in_rosy === false && <span className="ml-2 text-[10px] text-slate-600 bg-slate-200 px-1.5 py-0.5 rounded">tidak ada di ROSY</span>}
                    {e.data_issues?.length > 0 && <span title={e.data_issues.map((i) => DATA_ISSUE_LABELS[i] || i).join(", ")} className="ml-2 text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded" data-testid={`employee-issues-${e.nik}`}>⚠ {e.data_issues.length}</span>}
                    <div className="text-xs font-normal text-slate-500">{e.email}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{e.department}{e.position && <div className="text-xs text-slate-500">{e.position}</div>}</td>
                  <td className="px-4 py-3">{e.gender}</td>
                  <td className="px-4 py-3 num">{e.ptkp_status || `${e.marital_status}/${e.dependents_count}`}{e.has_husband_certificate ? " ✓SK" : ""}</td>
                  <td className="px-4 py-3 text-xs">{PAYROLL_STATUS_LABELS[e.payroll_status] || e.payroll_status}</td>
                  <td className="px-4 py-3 num">{rp(e.basic_salary)}</td>
                  <td className="px-4 py-3 num">{rp(e.position_allowance)}</td>
                  <td className="px-4 py-3 num">{rp(e.monthly_attendance_allowance)}</td>
                  <td className="px-4 py-3 num" data-testid={`employee-ot-rate-${e.nik}`}>{rp(e.overtime_hourly_rate)}</td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap">{bpjsText(e)}</td>
                  <td className="px-4 py-3 num text-xs whitespace-nowrap">{e.bank_name} {e.bank_account_number}</td>
                  <td className="px-4 py-3 num text-[11px] text-slate-500 whitespace-nowrap">{e.synced_at ? new Date(e.synced_at).toLocaleString("id-ID") : "seed"}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">{list.length ? "Tidak ada yang cocok." : "Belum ada data — klik \"Sinkron dari ROSY\"."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
