import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS } from "@/lib/format";
import { PageTitle, Panel } from "@/components/common";
import { IntegrationBadge } from "@/components/IntegrationBadge";

const COLS = ["NIK", "Nama", "Dept", "L/P", "PTKP Dasar", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rate Lembur/Jam", "BPJS", "Rekening", "Sinkron"];

export default function EmployeesView() {
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/hr/employees").then((r) => setList(r.data)); }, []);
  const rows = list.filter((e) => `${e.nik} ${e.name} ${e.department}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div>
      <PageTitle title="Data Karyawan & Gaji" subtitle="Hanya-lihat. Sumber data: ROSY — diperbarui otomatis saat membuat periode payroll baru">
        <IntegrationBadge system="rosy" />
        <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-1.5 bg-white w-64">
          <Search className="h-4 w-4 text-slate-400" />
          <input data-testid="employee-search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full" />
        </label>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="employees-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{COLS.map((h) => <th key={h} className="text-left px-4 py-3 whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50" data-testid={`employee-row-${e.nik}`}>
                  <td className="px-4 py-3 num">{e.nik}</td>
                  <td className="px-4 py-3 font-semibold whitespace-nowrap">{e.name}<div className="text-xs font-normal text-slate-500">{e.email}</div></td>
                  <td className="px-4 py-3 text-slate-600">{e.department}</td>
                  <td className="px-4 py-3">{e.gender}</td>
                  <td className="px-4 py-3 num">{e.marital_status}/{e.dependents_count}{e.has_husband_certificate ? " ✓SK" : ""}</td>
                  <td className="px-4 py-3 text-xs">{PAYROLL_STATUS_LABELS[e.payroll_status] || e.payroll_status}</td>
                  <td className="px-4 py-3 num">{rp(e.basic_salary)}</td>
                  <td className="px-4 py-3 num">{rp(e.position_allowance)}</td>
                  <td className="px-4 py-3 num">{rp(e.monthly_attendance_allowance)}</td>
                  <td className="px-4 py-3 num" data-testid={`employee-ot-rate-${e.nik}`}>{rp(e.overtime_hourly_rate)}</td>
                  <td className="px-4 py-3 text-xs">{[e.has_bpjs_kes !== false && "Kes", e.has_bpjs_tk !== false && "TK"].filter(Boolean).join(" + ") || "-"}</td>
                  <td className="px-4 py-3 num text-xs whitespace-nowrap">{e.bank_name} {e.bank_account_number}</td>
                  <td className="px-4 py-3 num text-[11px] text-slate-500 whitespace-nowrap">{e.synced_at ? new Date(e.synced_at).toLocaleString("id-ID") : "seed"}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={COLS.length} className="px-4 py-8 text-center text-slate-500">Tidak ada data.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
