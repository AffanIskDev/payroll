import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LogOut, ChevronRight, LogIn, Clock, CheckCircle2, Landmark, FileBadge, Download } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { rp } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";

const mask = (n) => (n ? `•••• ${n.slice(-4)}` : "-");

export default function EmployeeHome() {
  const { user, logout } = useAuth();
  const [slips, setSlips] = useState(null);
  const [profile, setProfile] = useState(null);
  const [today, setToday] = useState(null);
  const [forms, setForms] = useState([]);

  const loadToday = () => api.get("/v1/employee/attendance/today").then((r) => setToday(r.data));
  useEffect(() => {
    api.get("/v1/employee/payslips").then((r) => setSlips(r.data));
    api.get("/v1/employee/profile").then((r) => setProfile(r.data));
    api.get("/v1/employee/tax-forms/1721a1").then((r) => setForms(r.data));
    loadToday();
  }, []);

  const clock = async (kind) => {
    try {
      const { data } = await api.post(`/v1/employee/attendance/clock-${kind}`);
      toast.success(kind === "in" ? `Absen masuk ${data.check_in_time}` : `Absen pulang ${data.check_out_time}`);
      loadToday();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const downloadA1 = (y) => saveFile("get", `/v1/employee/tax-forms/1721a1/${y}/download`, `1721-A1_${y}.pdf`)
    .then(() => toast.success("Bukti potong diunduh. Buka dengan sandi DDMMYY."))
    .catch(async (e) => toast.error(await blobErrMsg(e)));

  const latest = slips?.[0];
  const log = today?.log;
  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-50 pb-16 sm:border-x border-slate-200" data-testid="employee-home">
      <div className="px-5 pt-6 pb-4 flex items-center justify-between">
        <div>
          <div className="text-xs text-teal-700 font-semibold tracking-wider uppercase">Rumatku</div>
          <div className="text-lg font-bold" data-testid="employee-greeting">Halo, {user?.name?.split(" ")[0]}</div>
        </div>
        <button data-testid="employee-logout-button" onClick={logout} className="p-2 rounded-full bg-white border border-slate-200"><LogOut className="h-4 w-4" /></button>
      </div>
      <div className="px-4">
        {latest ? (
          <Link to={`/me/payslip/${latest.id}`} data-testid="hero-thp-card" className="block relative overflow-hidden rounded-2xl text-white p-6 shadow-lg fade-up" style={{ background: "linear-gradient(135deg,#0F766E 0%,#0D9488 55%,#14B8A6 100%)" }}>
            <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
            <div className="absolute -right-4 bottom-0 h-24 w-24 rounded-full bg-white/5" />
            <div className="text-sm text-teal-50">Gaji {latest.period.period_name}</div>
            <div className="num text-3xl font-extrabold mt-1 tracking-tight" data-testid="hero-thp-amount">{rp(latest.take_home_pay)}</div>
            <div className="flex items-center gap-2 mt-4 text-xs">
              <span className="inline-flex items-center gap-1 bg-white/20 rounded-full px-2.5 py-1"><CheckCircle2 className="h-3.5 w-3.5" /> Dijadwalkan transfer {latest.period.payment_date}</span>
            </div>
            <div className="flex items-center justify-between mt-4 text-xs text-teal-50">
              <span className="inline-flex items-center gap-1.5"><Landmark className="h-3.5 w-3.5" /> {profile?.bank_name} {mask(profile?.bank_account_number)}</span>
              <ChevronRight className="h-4 w-4" />
            </div>
          </Link>
        ) : (
          <div className="rounded-2xl bg-white border border-slate-200 p-6 text-sm text-slate-500" data-testid="no-payslip">{slips ? "Belum ada slip gaji yang disetujui HRD." : "Memuat..."}</div>
        )}
      </div>
      <div className="px-4 mt-5">
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="clock-card">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold"><Clock className="h-4 w-4 text-teal-600" /> Presensi Hari Ini</div>
            <span className="num text-xs text-slate-500">{today?.day_name}, {today?.date}</span>
          </div>
          <div className="mt-2 text-xs text-slate-600" data-testid="today-schedule">
            {today && (today.shifts.length
              ? today.shifts.map((s) => `${s.name} ${s.start}–${s.end}`).join(" · ")
              : "Hari libur sesuai jadwal")}
            <div className="text-[11px] text-slate-400">{today?.schedule_name}</div>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <button data-testid="clock-in-button" disabled={!!log?.check_in_time} onClick={() => clock("in")} className="rounded-xl bg-teal-600 hover:bg-teal-700 text-white py-3 text-sm font-semibold disabled:bg-slate-200 disabled:text-slate-500 flex items-center justify-center gap-1.5"><LogIn className="h-4 w-4" /> {log?.check_in_time ? `Masuk ${log.check_in_time}` : "Absen Masuk"}</button>
            <button data-testid="clock-out-button" disabled={!!log?.check_out_time} onClick={() => clock("out")} className="rounded-xl border-2 border-teal-600 text-teal-700 py-3 text-sm font-semibold disabled:border-slate-200 disabled:text-slate-500 flex items-center justify-center gap-1.5"><LogOut className="h-4 w-4" /> {log?.check_out_time ? `Pulang ${log.check_out_time}` : "Absen Pulang"}</button>
          </div>
          {log && (log.minutes_late > 0 || log.minutes_early_leave > 0) && <div className="mt-2 text-xs text-rose-600" data-testid="clock-late-info">Terlambat {log.minutes_late} m · Pulang cepat {log.minutes_early_leave} m</div>}
        </div>
      </div>
      <div className="px-4 mt-6">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 px-1">Riwayat Slip Gaji</div>
        <div className="space-y-2" data-testid="payslip-history">
          {slips?.map((s) => (
            <Link key={s.id} to={`/me/payslip/${s.id}`} data-testid={`history-${s.id}`} className="flex items-center justify-between bg-white rounded-xl border border-slate-200 px-4 py-3 hover:border-teal-400 transition-colors">
              <div>
                <div className="text-sm font-semibold">{s.period.period_name}</div>
                <div className="text-[11px] text-slate-500">Transfer {s.period.payment_date}</div>
              </div>
              <div className="flex items-center gap-2"><span className="num text-sm font-bold text-teal-700">{rp(s.take_home_pay)}</span><ChevronRight className="h-4 w-4 text-slate-400" /></div>
            </Link>
          ))}
        </div>
      </div>
      {!!forms.length && (
        <div className="px-4 mt-6">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 px-1">Bukti Potong Pajak 1721-A1</div>
          <div className="space-y-2" data-testid="a1-list">
            {forms.map((f) => (
              <button key={f.tax_year} data-testid={`a1-employee-download-${f.tax_year}`} onClick={() => downloadA1(f.tax_year)} className="w-full flex items-center justify-between bg-white rounded-xl border border-slate-200 px-4 py-3 hover:border-teal-400 transition-colors text-left">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-lg bg-teal-50 grid place-items-center"><FileBadge className="h-4 w-4 text-teal-700" /></div>
                  <div>
                    <div className="text-sm font-semibold">Tahun Pajak {f.tax_year}{!f.is_complete && <span className="ml-2 text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">Sementara</span>}</div>
                    <div className="text-[11px] text-slate-500 num">PPh 21 dipotong {rp(f.items.i20)}</div>
                  </div>
                </div>
                <Download className="h-4 w-4 text-teal-700" />
              </button>
            ))}
          </div>
          <div className="text-[11px] text-slate-500 mt-2 px-1">PDF dilindungi sandi 6 digit tanggal lahir Anda (DDMMYY)</div>
        </div>
      )}
    </div>
  );
}
