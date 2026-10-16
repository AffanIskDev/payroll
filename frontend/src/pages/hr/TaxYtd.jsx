import { useEffect, useRef, useState, useCallback } from "react";
import { Upload, FileDown, Trash2, Info } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";

export default function TaxYtd() {
  const [year, setYear] = useState(2026);
  const [rows, setRows] = useState([]);
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const load = useCallback(() => api.get("/hr/tax-balances", { params: { year } }).then((r) => setRows(r.data)), [year]);
  useEffect(() => { load(); }, [load]);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post("/hr/tax-balances/import", fd);
      setErrors(data.errors);
      toast.success(`${data.imported} baris diimpor${data.errors.length ? `, ${data.errors.length} error` : ""}`);
      load();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); e.target.value = ""; }
  };
  const template = () => saveFile("get", "/hr/tax-balances/template", "template.csv").catch(async (e) => toast.error(await blobErrMsg(e)));
  const del = (id) => api.delete(`/hr/tax-balances/${id}`).then(load).catch((e) => toast.error(errMsg(e)));

  return (
    <div>
      <PageTitle title="Saldo Awal Pajak YTD" subtitle="employee_tax_initial_balances — dipakai untuk rekonsiliasi PPh 21 Desember (Pasal 17)">
        <select data-testid="ytd-year-select" value={year} onChange={(e) => setYear(Number(e.target.value))} className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
          {[2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <Btn variant="outline" onClick={template} data-testid="ytd-template-button"><FileDown className="h-4 w-4" /> Template CSV</Btn>
        <Btn onClick={() => fileRef.current?.click()} disabled={busy} data-testid="ytd-import-button"><Upload className="h-4 w-4" /> {busy ? "Mengimpor..." : "Impor CSV / Excel"}</Btn>
        <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={upload} data-testid="ytd-file-input" />
      </PageTitle>
      <div className="mb-4 flex gap-2 text-xs bg-brand-50 border border-brand-200 text-brand-700 rounded-md px-4 py-3">
        <Info className="h-4 w-4 shrink-0" />
        <span>Kolom: nik, tax_year, cutoff_month (1–11), ptkp_status, gross_income_ytd (bruto pajak), employee_jht_jp_ytd, biaya_jabatan_ytd, pph21_paid_ytd, notes. Saldo awal mencakup Januari s/d cutoff_month; bulan setelahnya diambil dari slip di sistem.</span>
      </div>
      {!!errors.length && (
        <div className="mb-4 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded-md px-4 py-3 space-y-0.5" data-testid="ytd-import-errors">
          {errors.map((e) => <div key={e}>{e}</div>)}
        </div>
      )}
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="ytd-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>{["NIK", "Nama", "Cutoff", "PTKP", "Bruto YTD", "JHT+JP Pekerja", "Biaya Jabatan", "PPh 21 Dibayar", "Catatan", ""].map((h) => <th key={h} className="text-left px-4 py-3">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.id} data-testid={`ytd-row-${r.nik}`} className="hover:bg-slate-50">
                  <td className="px-4 py-3 num">{r.nik}</td>
                  <td className="px-4 py-3 font-semibold">{r.name}</td>
                  <td className="px-4 py-3 num">Jan–{r.cutoff_month}</td>
                  <td className="px-4 py-3 num">{r.ptkp_status}</td>
                  <td className="px-4 py-3 num">{rp(r.gross_income_ytd)}</td>
                  <td className="px-4 py-3 num">{rp(r.employee_jht_jp_ytd)}</td>
                  <td className="px-4 py-3 num">{rp(r.biaya_jabatan_ytd)}</td>
                  <td className="px-4 py-3 num">{rp(r.pph21_paid_ytd)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{r.notes}</td>
                  <td className="px-4 py-3"><button data-testid={`ytd-delete-${r.nik}`} onClick={() => del(r.id)} className="p-1 rounded hover:bg-rose-50 text-rose-600"><Trash2 className="h-4 w-4" /></button></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={10} className="px-4 py-8 text-center text-slate-500">Belum ada saldo awal untuk tahun {year}.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
