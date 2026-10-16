import { useEffect, useState } from "react";
import { FileDown } from "lucide-react";
import { api } from "@/lib/api";
import { rp, SLIP_STATUS, jamMenit } from "@/lib/format";
import { PageTitle, Panel, Btn, StatusBadge } from "@/components/common";

const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

export default function OvertimeRecap() {
  const [month, setMonth] = useState(thisMonth());
  const [d, setD] = useState(null);
  const [delim, setDelim] = useState(",");
  useEffect(() => { api.get("/hr/configs").then((r) => { const v = r.data.find((c) => c.config_key === "CSV_DELIMITER")?.config_value || ","; setDelim(v === "tab" ? "\t" : v); }); }, []);
  useEffect(() => { if (month) api.get("/hr/overtime-recap", { params: { month } }).then((r) => setD(r.data)); }, [month]);

  const exportCsv = () => {
    const head = ["NIK", "Nama", "Departemen", "Periode", "Jam Lembur", "Menit Lembur", "Rate (Rp/jam)", "Nominal Lembur", "Status Slip"];
    const lines = d.rows.map((r) => [r.nik, r.name, r.department || "", r.period_name, jamMenit(r.overtime_hours), Math.round((r.overtime_hours || 0) * 60), r.overtime_rate, r.overtime_pay, r.slip_status]);
    const csv = [head, ...lines].map((l) => l.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(delim)).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `Rekap_Lembur_${month}.csv`;
    a.click();
  };

  return (
    <div>
      <PageTitle title="Rekap Lembur Bulanan" subtitle="Jam & nominal lembur per karyawan dari slip periode yang berakhir di bulan ini">
        <input data-testid="ot-month-input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="border border-slate-300 rounded-md px-3 py-2 text-sm" />
        <Btn variant="outline" data-testid="ot-export-button" onClick={exportCsv} disabled={!d?.rows.length}><FileDown className="h-4 w-4" /> Ekspor CSV</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="ot-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>{["Petugas", "Periode", "Jam Lembur", "Rate / Jam", "Nominal", "Status"].map((h, i) => <th key={h} className={`px-4 py-3 ${i > 1 && i < 5 ? "text-right" : "text-left"}`}>{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {d?.rows.map((r) => (
                <tr key={`${r.employee_id}-${r.period_name}`} data-testid={`ot-row-${r.nik}`} className="hover:bg-slate-50">
                  <td className="px-4 py-3"><div className="font-semibold">{r.name}</div><div className="text-xs text-slate-500 num">{r.nik} · {r.department}</div></td>
                  <td className="px-4 py-3">{r.period_name}</td>
                  <td className={`px-4 py-3 num text-right ${!r.overtime_hours ? "text-slate-300" : ""}`}>{r.overtime_hours ? jamMenit(r.overtime_hours) : 0}</td>
                  <td className="px-4 py-3 num text-right">{rp(r.overtime_rate)}</td>
                  <td className="px-4 py-3 num text-right font-semibold">{rp(r.overtime_pay)}</td>
                  <td className="px-4 py-3"><StatusBadge map={SLIP_STATUS} status={r.slip_status} /></td>
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Belum ada slip payroll untuk bulan ini.</td></tr>}
            </tbody>
            {!!d?.rows.length && (
              <tfoot className="bg-slate-50 font-semibold">
                <tr>
                  <td colSpan={2} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Total</td>
                  <td className="px-4 py-3 num text-right" data-testid="ot-total-hours">{jamMenit(d.total_hours)}</td>
                  <td />
                  <td className="px-4 py-3 num text-right" data-testid="ot-total-pay">{rp(d.total_pay)}</td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Panel>
    </div>
  );
}
