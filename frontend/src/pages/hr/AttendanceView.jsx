import { useEffect, useState, useCallback } from "react";
import { Camera, MapPin } from "lucide-react";
import { api } from "@/lib/api";
import { LEAVE_LABELS, jamMenit, localIso } from "@/lib/format";
import { PageTitle, Panel } from "@/components/common";
import { EmployeeSearch } from "@/components/EmployeeSearch";

const inp = "border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white w-40";
const Evidence = ({ photo, loc, tid }) => (
  <span className="inline-flex items-center gap-1">
    {photo && <a data-testid={`${tid}-photo`} href={photo} target="_blank" rel="noreferrer" className="text-teal-700" title="Foto wajah"><Camera className="h-3.5 w-3.5" /></a>}
    {loc && <a data-testid={`${tid}-location`} href={`https://www.google.com/maps?q=${encodeURIComponent(loc)}`} target="_blank" rel="noreferrer" className="text-blue-800" title={loc}><MapPin className="h-3.5 w-3.5" /></a>}
  </span>
);

// bulan berjalan, dipakai hanya bila belum ada periode payroll
const thisMonth = () => {
  const d = new Date();
  return { start: localIso(new Date(d.getFullYear(), d.getMonth(), 1)), end: localIso(new Date(d.getFullYear(), d.getMonth() + 1, 0)) };
};

export default function AttendanceView() {
  const [emps, setEmps] = useState([]);
  const [eid, setEid] = useState("");
  const [range, setRange] = useState(thisMonth);
  const [logs, setLogs] = useState([]);
  // tidak memilih karyawan pertama otomatis (user 12 Okt 2026): kolom cari kosong sampai HRD mengetik nama/NIK;
  // rentang tanggal bawaan mengikuti periode payroll terbaru (daftar periode sudah terurut terbaru dulu)
  useEffect(() => {
    api.get("/hr/employees").then((r) => setEmps(r.data));
    api.get("/hr/periods").then((r) => { const p = r.data[0]; if (p) setRange({ start: p.start_date, end: p.end_date }); });
  }, []);
  const load = useCallback(() => {
    if (eid) api.get("/hr/attendance", { params: { employee_id: eid, ...range } }).then((r) => setLogs(r.data));
    else setLogs([]);
  }, [eid, range]);
  useEffect(() => { load(); }, [load]);
  const sumOt = logs.reduce((a, l) => a + (l.overtime_hours || 0), 0);

  return (
    <div>
      <PageTitle title="Log Presensi Harian" subtitle="Hanya-lihat. Sumber: RUMATKU lewat ROSY — diperbarui dengan tombol 'Sinkron dari ROSY' di Dashboard">
        <EmployeeSearch employees={emps} value={eid} onChange={setEid} />
        <input data-testid="attendance-start-input" type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} className={inp} />
        <input data-testid="attendance-end-input" type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} className={inp} />
      </PageTitle>
      <Panel title={eid ? `${logs.length} log · lembur ${jamMenit(sumOt)}` : "Log presensi"}>
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
                  <td className="px-4 py-2">{l.overtime_hours ? jamMenit(l.overtime_hours, true) : "-"}</td>
                  <td className="px-4 py-2 text-xs font-sans">{LEAVE_LABELS[l.leave_type] || l.leave_type}</td>
                </tr>
              ))}
              {!logs.length && <tr><td colSpan={9} className="px-4 py-6 text-center text-slate-500 font-sans">{eid ? "Tidak ada log pada rentang ini." : "Pilih karyawan dulu — ketik nama atau NIK di kolom cari."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
