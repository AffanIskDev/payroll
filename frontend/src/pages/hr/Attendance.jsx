import { useEffect, useState, useCallback } from "react";
import { Trash2, Save, Camera, MapPin } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { LEAVE_LABELS } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";
import { AttendanceImport } from "@/components/AttendanceImport";
import { EmployeeSearch } from "@/components/EmployeeSearch";

const mapUrl = (loc) => `https://www.google.com/maps?q=${encodeURIComponent(loc)}`;
const Evidence = ({ photo, loc, tid }) => (
  <span className="inline-flex items-center gap-1">
    {photo && <a data-testid={`${tid}-photo`} href={photo} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-teal-700 hover:text-teal-900" title="Foto wajah"><Camera className="h-3.5 w-3.5" /></a>}
    {loc && <a data-testid={`${tid}-location`} href={mapUrl(loc)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-blue-800 hover:text-blue-950" title={loc}><MapPin className="h-3.5 w-3.5" /></a>}
  </span>
);

const BLANK = { work_date: "", check_in_time: "", check_out_time: "", minutes_late: "", minutes_early_leave: "", is_missing_check_in: false, is_missing_check_out: false, leave_type: "present", shift_code: "", notes: "" };
const inp = "w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white";

export default function Attendance() {
  const [emps, setEmps] = useState([]);
  const [eid, setEid] = useState("");
  const [range, setRange] = useState({ start: "2026-03-01", end: "2026-03-31" });
  const [logs, setLogs] = useState([]);
  const [f, setF] = useState(BLANK);
  const [schedules, setSchedules] = useState([]);

  useEffect(() => {
    api.get("/hr/schedules").then((r) => setSchedules(r.data));
    api.get("/hr/employees").then((r) => { setEmps(r.data); if (r.data[0]) setEid(r.data[0].id); });
  }, []);
  const load = useCallback(() => {
    if (eid) api.get("/hr/attendance", { params: { employee_id: eid, ...range } }).then((r) => setLogs(r.data));
  }, [eid, range]);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault();
    const body = { ...f, employee_id: eid };
    ["minutes_late", "minutes_early_leave"].forEach((k) => (body[k] = body[k] === "" ? null : Number(body[k])));
    ["check_in_time", "check_out_time", "shift_code"].forEach((k) => (body[k] = body[k] || null));
    try {
      await api.post("/hr/attendance", body);
      toast.success("Log presensi tersimpan. Jalankan ulang Proses Payroll untuk memperbarui slip.");
      setF(BLANK);
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };
  const del = async (id) => {
    await api.delete(`/hr/attendance/${id}`).catch((e) => toast.error(errMsg(e)));
    load();
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const emp = emps.find((e) => e.id === eid);
  const sched = schedules.find((s) => s.code === (emp?.work_schedule_code || "KANTOR_PUSAT"));

  return (
    <div>
      <PageTitle title="Log Presensi Harian" subtitle="Data otomatis dari Rumatku (clock-in/out) & koreksi manual HRD">
        <EmployeeSearch employees={emps} value={eid} onChange={setEid} />
        <input data-testid="attendance-start-input" type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} className={`${inp} w-40`} />
        <input data-testid="attendance-end-input" type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} className={`${inp} w-40`} />
      </PageTitle>
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
        <Panel title={`${logs.length} log`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="attendance-table">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                <tr>{["Tanggal", "Jadwal", "Masuk", "Pulang", "Telat", "Pulang Cepat", "Lupa Tap", "Jenis", "Sumber", ""].map((h) => <th key={h} className="text-left px-4 py-2.5">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100 num">
                {logs.map((l) => (
                  <tr key={l.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => setF({ ...BLANK, ...l, shift_code: l.shift_source === "manual" ? l.shift_code : "", check_in_time: l.check_in_time || "", check_out_time: l.check_out_time || "" })} data-testid={`attendance-row-${l.work_date}`}>
                    <td className="px-4 py-2">{l.work_date}</td>
                    <td className="px-4 py-2 text-xs">{l.is_off_day ? <span className="text-slate-400 font-sans">Libur</span> : l.schedule_start ? <span title={`sumber: ${l.shift_source || "auto"}`}>{l.shift_code} {l.schedule_start}–{l.schedule_end}{l.shift_source === "rotation" && <span className="ml-1 text-[9px] font-sans font-bold text-indigo-600">ROT</span>}{l.shift_source === "manual" && <span className="ml-1 text-[9px] font-sans font-bold text-amber-600">HRD</span>}</span> : "-"}</td>
                    <td className="px-4 py-2"><span className="inline-flex items-center gap-1.5">{l.check_in_time || "-"}<Evidence photo={l.photo_in_url} loc={l.location_in} tid={`att-in-${l.work_date}`} /></span></td>
                    <td className="px-4 py-2"><span className="inline-flex items-center gap-1.5">{l.check_out_time || "-"}<Evidence photo={l.photo_out_url} loc={l.location_out} tid={`att-out-${l.work_date}`} /></span></td>
                    <td className={`px-4 py-2 ${l.minutes_late >= 60 ? "text-rose-600 font-bold" : l.minutes_late ? "text-rose-600" : ""}`}>{l.minutes_late || 0} m</td>
                    <td className={`px-4 py-2 ${l.minutes_early_leave ? "text-rose-600" : ""}`}>{l.minutes_early_leave || 0} m</td>
                    <td className="px-4 py-2 text-xs">{[l.is_missing_check_in && "IN", l.is_missing_check_out && "OUT"].filter(Boolean).join("/") || "-"}</td>
                    <td className="px-4 py-2 text-xs font-sans">{LEAVE_LABELS[l.leave_type]}</td>
                    <td className="px-4 py-2 text-xs text-slate-500">{l.source}</td>
                    <td className="px-4 py-2"><button data-testid={`delete-attendance-${l.work_date}`} onClick={(e) => { e.stopPropagation(); del(l.id); }} className="p-1 rounded hover:bg-rose-50 text-rose-600"><Trash2 className="h-4 w-4" /></button></td>
                  </tr>
                ))}
                {!logs.length && <tr><td colSpan={10} className="px-4 py-6 text-center text-slate-500 font-sans">Tidak ada log pada rentang ini.</td></tr>}
              </tbody>
            </table>
          </div>
        </Panel>
        <div className="space-y-6">
        <AttendanceImport onDone={load} />
        <Panel title="Input / Koreksi Manual">
          <form onSubmit={save} className="p-5 space-y-3" data-testid="attendance-form">
            <label className="block text-xs font-semibold text-slate-500 uppercase">Tanggal<input data-testid="att-date-input" type="date" required value={f.work_date} onChange={set("work_date")} className={inp} /></label>
            <label className="block text-xs font-semibold text-slate-500 uppercase">Jenis Kehadiran
              <select data-testid="att-leave-select" value={f.leave_type} onChange={set("leave_type")} className={inp}>{Object.entries(LEAVE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </label>
            <label className="block text-xs font-semibold text-slate-500 uppercase">Shift ({sched?.code || "-"})
              <select data-testid="att-shift-select" value={f.shift_code} onChange={set("shift_code")} className={inp}>
                <option value="">Otomatis (jam masuk terdekat)</option>
                {sched?.shifts.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs font-semibold text-slate-500 uppercase">Jam Masuk<input data-testid="att-checkin-input" type="time" value={f.check_in_time} onChange={set("check_in_time")} className={inp} /></label>
              <label className="block text-xs font-semibold text-slate-500 uppercase">Jam Pulang<input data-testid="att-checkout-input" type="time" value={f.check_out_time} onChange={set("check_out_time")} className={inp} /></label>
              <label className="block text-xs font-semibold text-slate-500 uppercase">Menit Telat<input data-testid="att-late-input" type="number" min="0" placeholder="auto" value={f.minutes_late} onChange={set("minutes_late")} className={inp} /></label>
              <label className="block text-xs font-semibold text-slate-500 uppercase">Menit Pulang Cepat<input data-testid="att-early-input" type="number" min="0" placeholder="auto" value={f.minutes_early_leave} onChange={set("minutes_early_leave")} className={inp} /></label>
            </div>
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2"><input data-testid="att-missing-in-checkbox" type="checkbox" checked={f.is_missing_check_in} onChange={set("is_missing_check_in")} /> Lupa tap-in</label>
              <label className="flex items-center gap-2"><input data-testid="att-missing-out-checkbox" type="checkbox" checked={f.is_missing_check_out} onChange={set("is_missing_check_out")} /> Lupa tap-out</label>
            </div>
            <p className="text-[11px] text-slate-400">Kosongkan menit untuk dihitung otomatis dari jadwal kerja karyawan (menu Jadwal). Hari libur jadwal = tanpa denda.</p>
            <Btn data-testid="att-submit-button" className="w-full justify-center"><Save className="h-4 w-4" /> Simpan Log</Btn>
          </form>
        </Panel>
        </div>
      </div>
    </div>
  );
}
