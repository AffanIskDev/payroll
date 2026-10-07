import { useEffect, useState, useCallback } from "react";
import { Camera, MapPin } from "lucide-react";
import { api } from "@/lib/api";
import { LEAVE_LABELS } from "@/lib/format";
import { PageTitle, Panel } from "@/components/common";
import { EmployeeSearch } from "@/components/EmployeeSearch";
import { IntegrationBadge } from "@/components/IntegrationBadge";

const inp = "border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white w-40";
const Evidence = ({ photo, loc, tid }) => (
  <span className="inline-flex items-center gap-1">
    {photo && <a data-testid={`${tid}-photo`} href={photo} target="_blank" rel="noreferrer" className="text-teal-700" title="Foto wajah"><Camera className="h-3.5 w-3.5" /></a>}
    {loc && <a data-testid={`${tid}-location`} href={`https://www.google.com/maps?q=${encodeURIComponent(loc)}`} target="_blank" rel="noreferrer" className="text-blue-800" title={loc}><MapPin className="h-3.5 w-3.5" /></a>}
  </span>
);

export default function AttendanceView() {
  const [emps, setEmps] = useState([]);
  const [eid, setEid] = useState("");
  const [range, setRange] = useState({ start: "2026-03-01", end: "2026-03-31" });
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/hr/employees").then((r) => { setEmps(r.data); if (r.data[0]) setEid(r.data[0].id); }); }, []);
  const load = useCallback(() => {
    if (eid) api.get("/hr/attendance", { params: { employee_id: eid, ...range } }).then((r) => setLogs(r.data));
  }, [eid, range]);
  useEffect(() => { load(); }, [load]);
  const sumOt = logs.reduce((a, l) => a + (l.overtime_hours || 0), 0);

  return (
    <div>
      <PageTitle title="Log Presensi Harian" subtitle="Hanya-lihat. Sumber: RUMATKU — diambil lewat tombol 'Ambil Data Absensi' di periode payroll">
        <IntegrationBadge system="rumatku" />
        <EmployeeSearch employees={emps} value={eid} onChange={setEid} />
        <input data-testid="attendance-start-input" type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} className={inp} />
        <input data-testid="attendance-end-input" type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} className={inp} />
      </PageTitle>
      <Panel title={`${logs.length} log · lembur ${sumOt} jam`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="attendance-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{["Tanggal", "Shift", "Masuk", "Pulang", "Telat", "Pulang Cepat", "Lupa Tap", "Lembur", "Jenis"].map((h) => <th key={h} className="text-left px-4 py-2.5">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100 num">
              {logs.map((l) => (
                <tr key={l.id} className="hover:bg-slate-50" data-testid={`attendance-row-${l.work_date}`}>
                  <td className="px-4 py-2">{l.work_date}</td>
                  <td className="px-4 py-2 text-xs">{l.is_off_day ? <span className="text-slate-400 font-sans">Libur</span> : l.schedule_start ? `${l.shift_code} ${l.schedule_start}–${l.schedule_end}` : "-"}</td>
                  <td className="px-4 py-2"><span className="inline-flex items-center gap-1.5">{l.check_in_time || "-"}<Evidence photo={l.photo_in_url} loc={l.location_in} tid={`att-in-${l.work_date}`} /></span></td>
                  <td className="px-4 py-2"><span className="inline-flex items-center gap-1.5">{l.check_out_time || "-"}<Evidence photo={l.photo_out_url} loc={l.location_out} tid={`att-out-${l.work_date}`} /></span></td>
                  <td className={`px-4 py-2 ${l.minutes_late >= 60 ? "text-rose-600 font-bold" : l.minutes_late ? "text-rose-600" : ""}`}>{l.minutes_late || 0} m</td>
                  <td className={`px-4 py-2 ${l.minutes_early_leave ? "text-rose-600" : ""}`}>{l.minutes_early_leave || 0} m</td>
                  <td className="px-4 py-2 text-xs">{[l.is_missing_check_in && "IN", l.is_missing_check_out && "OUT"].filter(Boolean).join("/") || "-"}</td>
                  <td className="px-4 py-2">{l.overtime_hours ? `${l.overtime_hours} j` : "-"}</td>
                  <td className="px-4 py-2 text-xs font-sans">{LEAVE_LABELS[l.leave_type] || l.leave_type}</td>
                </tr>
              ))}
              {!logs.length && <tr><td colSpan={9} className="px-4 py-6 text-center text-slate-500 font-sans">Tidak ada log pada rentang ini.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
