import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PageTitle, Panel, Btn } from "@/components/common";

const DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
const t = "border border-slate-300 rounded px-1.5 py-1 text-xs num bg-white w-[92px]";

function ScheduleCard({ sched, onSaved }) {
  const [s, setS] = useState(sched);
  const setDay = (si, d, field, v) => {
    const shifts = s.shifts.map((sh, i) => {
      if (i !== si) return sh;
      const day = { ...(sh.days[d] || { start: "", end: "" }), [field]: v };
      return { ...sh, days: { ...sh.days, [d]: day } };
    });
    setS({ ...s, shifts });
  };
  const save = async () => {
    try {
      const { data } = await api.put(`/hr/schedules/${s.code}`, { name: s.name, shifts: s.shifts });
      setS(data);
      toast.success(`Jadwal ${data.code} disimpan`);
      onSaved();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Panel title={s.code} right={<Btn data-testid={`save-schedule-${s.code}`} onClick={save}><Save className="h-4 w-4" /> Simpan</Btn>}>
      <div className="p-5 space-y-3" data-testid={`schedule-card-${s.code}`}>
        <input data-testid={`schedule-name-${s.code}`} value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm font-semibold" />
        <div className="overflow-x-auto">
          <table className="text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr><th className="text-left pr-4 py-2">Hari</th>{s.shifts.map((sh) => <th key={sh.code} className="text-left px-2 py-2">{sh.name} ({sh.code})</th>)}</tr>
            </thead>
            <tbody>
              {DAYS.map((name, d) => (
                <tr key={d} className="border-t border-slate-100">
                  <td className="pr-4 py-1.5 font-medium">{name}</td>
                  {s.shifts.map((sh, si) => {
                    const day = sh.days[String(d)] || {};
                    const off = !day.start && !day.end;
                    return (
                      <td key={sh.code} className="px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          <input data-testid={`sched-${s.code}-${sh.code}-${d}-start`} type="time" value={day.start || ""} onChange={(e) => setDay(si, String(d), "start", e.target.value)} className={t} />
                          <span className="text-slate-400">–</span>
                          <input data-testid={`sched-${s.code}-${sh.code}-${d}-end`} type="time" value={day.end || ""} onChange={(e) => setDay(si, String(d), "end", e.target.value)} className={t} />
                          {off && <span className="text-[10px] font-semibold text-slate-400 uppercase ml-1">Libur</span>}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}

export default function Schedules() {
  const [list, setList] = useState(null);
  const load = () => api.get("/hr/schedules").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  return (
    <div>
      <PageTitle title="Jadwal Kerja & Shift" subtitle="Dasar perhitungan menit terlambat / pulang cepat. Kosongkan jam = hari libur." />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {list?.map((s) => <ScheduleCard key={s.code} sched={s} onSaved={load} />)}
      </div>
      <p className="text-xs text-slate-500 mt-4">Untuk jadwal 2 shift, shift dipilih otomatis berdasarkan jam masuk terdekat (bisa dipilih manual oleh HRD di menu Absensi). Perubahan jadwal berlaku untuk log presensi baru; log lama tidak dihitung ulang.</p>
    </div>
  );
}
