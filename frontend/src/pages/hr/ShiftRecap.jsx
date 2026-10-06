import { useEffect, useState } from "react";
import { FileDown, Info } from "lucide-react";
import { api } from "@/lib/api";
import { PageTitle, Panel, Btn } from "@/components/common";

const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

export default function ShiftRecap() {
  const [month, setMonth] = useState(thisMonth());
  const [d, setD] = useState(null);
  useEffect(() => { if (month) api.get("/hr/shift-recap", { params: { month } }).then((r) => setD(r.data)); }, [month]);

  const cols = d ? [...d.shift_codes.map((c) => [c, d.shift_names[c]]), ["worked_on_off_day", "Masuk Hari Libur"], ["total_worked", "Total Masuk"], ["scheduled_off", "Libur Jadwal"], ["leave", "Cuti / Izin"], ["no_log", "Tanpa Log"]] : [];
  const val = (r, k) => (d.shift_codes.includes(k) ? r.shifts[k] || 0 : r[k]);

  const exportCsv = () => {
    const head = ["NIK", "Nama", "Departemen", "Jadwal", ...cols.map((c) => c[1])];
    const lines = d.rows.map((r) => [r.nik, r.name, r.department || "", r.schedule_code, ...cols.map(([k]) => val(r, k))]);
    const csv = [head, ...lines].map((l) => l.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `Rekap_Shift_${month}.csv`;
    a.click();
  };

  return (
    <div>
      <PageTitle title="Rekap Shift Bulanan" subtitle="Jumlah hari per shift, libur, dan cuti per petugas — dasar tunjangan shift">
        <input data-testid="recap-month-input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="border border-slate-300 rounded-md px-3 py-2 text-sm" />
        <Btn variant="outline" data-testid="recap-export-button" onClick={exportCsv} disabled={!d?.rows.length}><FileDown className="h-4 w-4" /> Ekspor CSV</Btn>
      </PageTitle>
      <div className="mb-4 flex gap-2 text-xs bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-4 py-3">
        <Info className="h-4 w-4 shrink-0" />
        <span>Dihitung dari log presensi. "Libur Jadwal" = hari tanpa jam kerja di jadwal & tanpa log; "Masuk Hari Libur" = ada log di hari libur jadwal; "Tanpa Log" = hari kerja tanpa catatan presensi.</span>
      </div>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="recap-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="text-left px-4 py-3">Petugas</th>
                <th className="text-left px-4 py-3">Jadwal</th>
                {cols.map(([k, l]) => <th key={k} className="text-right px-4 py-3">{l}{d.shift_codes.includes(k) && <span className="num text-slate-400"> ({k})</span>}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {d?.rows.map((r) => (
                <tr key={r.employee_id} className="hover:bg-slate-50" data-testid={`recap-row-${r.nik}`}>
                  <td className="px-4 py-3"><div className="font-semibold">{r.name}</div><div className="text-xs text-slate-500 num">{r.nik} · {r.department}</div></td>
                  <td className="px-4 py-3 num text-xs">{r.schedule_code}</td>
                  {cols.map(([k]) => {
                    const v = val(r, k);
                    return <td key={k} data-testid={`recap-${r.nik}-${k}`} className={`px-4 py-3 num text-right ${k === "total_worked" ? "font-bold" : ""} ${!v ? "text-slate-300" : ""}`}>{v}</td>;
                  })}
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={cols.length + 2} className="px-4 py-8 text-center text-slate-500">Tidak ada karyawan.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
      {d && <p className="text-xs text-slate-500 mt-3 num">{d.month} · {d.days_in_month} hari</p>}
    </div>
  );
}
