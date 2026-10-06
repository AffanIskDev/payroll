import { useEffect, useState, useCallback } from "react";
import { FileDown, Info } from "lucide-react";
import { toast } from "sonner";
import { api, saveFile, blobErrMsg } from "@/lib/api";
import { rp } from "@/lib/format";
import { PageTitle, Panel } from "@/components/common";

export default function TaxForms() {
  const [year, setYear] = useState(2026);
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get("/hr/tax-forms/1721a1", { params: { year } }).then((r) => setRows(r.data)), [year]);
  useEffect(() => { load(); }, [load]);

  const pdf = (r) => saveFile("get", `/hr/tax-forms/1721a1/${r.employee_id}/pdf?year=${year}`, `1721-A1_${r.nik}_${year}.pdf`)
    .catch(async (e) => toast.error(await blobErrMsg(e)));

  return (
    <div>
      <PageTitle title="Bukti Potong 1721-A1" subtitle="Rekap tahunan dari slip approved + saldo awal YTD">
        <select data-testid="a1-year-select" value={year} onChange={(e) => setYear(Number(e.target.value))} className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
          {[2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </PageTitle>
      <div className="mb-4 flex gap-2 text-xs bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-4 py-3">
        <Info className="h-4 w-4 shrink-0" />
        <span>Hanya slip berstatus approved yang dihitung. Status "Sementara" berarti masa Desember belum di-approve. Nama & NPWP pemotong diatur di Konfigurasi.</span>
      </div>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="a1-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{["Nomor", "NIK", "Nama", "Masa", "PTKP", "Bruto", "Neto", "PKP", "PPh Terutang", "PPh Dipotong", "Selisih", "Status", ""].map((h) => <th key={h} className="text-left px-3 py-3">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows?.map((r) => (
                <tr key={r.employee_id} className="hover:bg-slate-50" data-testid={`a1-row-${r.nik}`}>
                  <td className="px-3 py-3 num text-xs">{r.number}</td>
                  <td className="px-3 py-3 num">{r.nik}</td>
                  <td className="px-3 py-3 font-semibold">{r.name}</td>
                  <td className="px-3 py-3 num">{String(r.masa_start).padStart(2, "0")}–{String(r.masa_end).padStart(2, "0")}</td>
                  <td className="px-3 py-3 num">{r.ptkp_status}</td>
                  <td className="px-3 py-3 num">{rp(r.items.i8)}</td>
                  <td className="px-3 py-3 num">{rp(r.items.i14)}</td>
                  <td className="px-3 py-3 num">{rp(r.items.i16)}</td>
                  <td className="px-3 py-3 num">{rp(r.items.i19)}</td>
                  <td className="px-3 py-3 num">{rp(r.items.i20)}</td>
                  <td className={`px-3 py-3 num ${r.difference > 0 ? "text-rose-600" : r.difference < 0 ? "text-emerald-600" : ""}`}>{rp(r.difference)}</td>
                  <td className="px-3 py-3">
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${r.is_complete ? "bg-emerald-50 text-emerald-700 border-emerald-300" : "bg-amber-50 text-amber-700 border-amber-300"}`}>{r.is_complete ? "Final" : "Sementara"}</span>
                  </td>
                  <td className="px-3 py-3"><button data-testid={`a1-download-${r.nik}`} onClick={() => pdf(r)} className="inline-flex items-center gap-1 text-blue-900 font-semibold hover:underline whitespace-nowrap"><FileDown className="h-4 w-4" /> PDF</button></td>
                </tr>
              ))}
              {rows && !rows.length && <tr><td colSpan={13} className="px-4 py-8 text-center text-slate-500">Belum ada data pajak untuk tahun {year}.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
