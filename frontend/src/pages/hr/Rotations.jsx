import { useEffect, useState, useCallback } from "react";
import { Save, Repeat, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PageTitle, Panel, Btn } from "@/components/common";

const monday = (d) => {
  const x = new Date(`${d}T00:00:00`);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x.toISOString().slice(0, 10) === d ? d : fmt(x);
};
const fmt = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
const addWeeks = (d, n) => { const x = new Date(`${d}T00:00:00`); x.setDate(x.getDate() + 7 * n); return fmt(x); };
const label = (d) => { const x = new Date(`${d}T00:00:00`); const e = new Date(x); e.setDate(e.getDate() + 6); return `${x.getDate()}/${x.getMonth() + 1} – ${e.getDate()}/${e.getMonth() + 1}`; };
const TONE = { S1: "bg-sky-50 border-sky-300 text-sky-800", S2: "bg-indigo-50 border-indigo-300 text-indigo-800" };

export default function Rotations() {
  const [start, setStart] = useState(monday(fmt(new Date())));
  const [d, setD] = useState(null);
  const [grid, setGrid] = useState({});
  const load = useCallback(() => api.get("/hr/shift-rotations", { params: { start, weeks: 4 } }).then((r) => {
    setD(r.data);
    setGrid(Object.fromEntries(r.data.assignments.map((a) => [`${a.employee_id}|${a.week_start}`, a.shift_code])));
  }), [start]);
  useEffect(() => { load(); }, [load]);

  const set = (eid, w, v) => setGrid({ ...grid, [`${eid}|${w}`]: v });
  const autoRotate = (e) => {
    const first = grid[`${e.id}|${d.weeks[0]}`];
    if (!first) return toast.error(`Isi shift minggu pertama untuk ${e.name}`);
    const codes = e.shifts.map((s) => s.code);
    const g = { ...grid };
    d.weeks.forEach((w, i) => { g[`${e.id}|${w}`] = codes[(codes.indexOf(first) + i) % codes.length]; });
    setGrid(g);
  };
  const save = async () => {
    const assignments = d.employees.flatMap((e) => d.weeks.map((w) => ({ employee_id: e.id, week_start: w, shift_code: grid[`${e.id}|${w}`] || null })));
    try {
      const { data } = await api.put("/hr/shift-rotations", { assignments });
      toast.success(`${data.saved} penugasan shift disimpan`);
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div>
      <PageTitle title="Rotasi Shift Mingguan" subtitle="Untuk petugas dengan jadwal multi-shift. Prioritas: pilihan manual HRD › rotasi › jam masuk terdekat">
        <Btn variant="outline" data-testid="rotation-prev-button" onClick={() => setStart(addWeeks(start, -4))}><ChevronLeft className="h-4 w-4" /></Btn>
        <input data-testid="rotation-start-input" type="date" value={start} onChange={(e) => e.target.value && setStart(monday(e.target.value))} className="border border-slate-300 rounded-md px-3 py-2 text-sm" />
        <Btn variant="outline" data-testid="rotation-next-button" onClick={() => setStart(addWeeks(start, 4))}><ChevronRight className="h-4 w-4" /></Btn>
        <Btn data-testid="rotation-save-button" onClick={save} disabled={!d?.employees.length}><Save className="h-4 w-4" /> Simpan Rotasi</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="rotation-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="text-left px-4 py-3">Petugas</th>
                {d?.weeks.map((w) => <th key={w} className="text-left px-3 py-3 num">Minggu {label(w)}</th>)}
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {d?.employees.map((e) => (
                <tr key={e.id} data-testid={`rotation-row-${e.nik}`}>
                  <td className="px-4 py-3"><div className="font-semibold">{e.name}</div><div className="text-xs text-slate-500 num">{e.nik} · {e.schedule_code}</div></td>
                  {d.weeks.map((w) => {
                    const v = grid[`${e.id}|${w}`] || "";
                    return (
                      <td key={w} className="px-3 py-3">
                        <select data-testid={`rotation-${e.nik}-${w}`} value={v} onChange={(ev) => set(e.id, w, ev.target.value)} className={`border rounded-md px-2 py-1.5 text-xs font-semibold w-32 ${TONE[v] || "bg-white border-slate-300 text-slate-500"}`}>
                          <option value="">Otomatis</option>
                          {e.shifts.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                        </select>
                      </td>
                    );
                  })}
                  <td className="px-3 py-3"><button data-testid={`rotation-auto-${e.nik}`} onClick={() => autoRotate(e)} className="inline-flex items-center gap-1 text-xs font-semibold text-blue-900 hover:underline whitespace-nowrap"><Repeat className="h-3.5 w-3.5" /> Selang-seling</button></td>
                </tr>
              ))}
              {d && !d.employees.length && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Belum ada karyawan dengan jadwal multi-shift. Atur Jadwal Kerja karyawan ke "Unit 2 Shift" di menu Karyawan.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
      <p className="text-xs text-slate-500 mt-3">"Selang-seling" mengisi 4 minggu bergantian mulai dari shift minggu pertama. Rotasi berlaku untuk absen baru (clock-in Rumatku, impor, input HRD); log lama tidak dihitung ulang.</p>
    </div>
  );
}
