import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Lock, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useAuth, isHr } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(identifier, password);
      nav(isHr(u) ? "/hr-manager" : "/me");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] bg-white">
      <div className="hidden lg:flex flex-col justify-between bg-slate-900 text-white p-12 relative overflow-hidden">
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px)", backgroundSize: "36px 36px" }} />
        <div className="relative flex items-center gap-3">
          <div className="h-10 w-10 rounded-md bg-blue-800 grid place-items-center"><Building2 className="h-5 w-5" /></div>
          <div>
            <div className="font-bold tracking-tight">HRIS ROSY</div>
            <div className="text-xs text-slate-400">Payroll Module · Rumatku</div>
          </div>
        </div>
        <div className="relative space-y-6 fade-up">
          <h1 className="text-4xl xl:text-5xl font-extrabold leading-tight tracking-tight">Penggajian otomatis,<br />presisi sampai rupiah.</h1>
          <p className="text-slate-400 max-w-md text-sm leading-relaxed">Waterfall denda disiplin, BPJS dengan floor UMK Kab. Bekasi, PPh 21 TER PP 58/2023, dan slip PDF terenkripsi DDMMYY.</p>
          <div className="grid grid-cols-3 gap-3 max-w-lg">
            {[["25", "hari kerja"], ["TER", "A · B · C"], ["AES", "PDF 256-bit"]].map(([a, b]) => (
              <div key={a} className="border border-slate-700 rounded-md p-3">
                <div className="num text-xl font-semibold text-emerald-400">{a}</div>
                <div className="text-xs text-slate-400">{b}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative text-xs text-slate-500">PP 35/2021 · PP 58/2023 · PMK 168/2023 · UU HPP 7/2021</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5 fade-up" data-testid="login-form">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Masuk</h2>
            <p className="text-sm text-slate-500 mt-1">Portal Manager HRD (ROSY) & Karyawan (Rumatku)</p>
          </div>
          <label className="block space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Email atau NIK</span>
            <input data-testid="login-identifier-input" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required className="w-full border border-slate-300 rounded-md px-3 py-2.5 text-sm outline-none focus:border-blue-800 focus:ring-2 focus:ring-blue-100" placeholder="hrd.manager@rumatku.id / EMP-001" />
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Password</span>
            <input data-testid="login-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="w-full border border-slate-300 rounded-md px-3 py-2.5 text-sm outline-none focus:border-blue-800 focus:ring-2 focus:ring-blue-100" />
          </label>
          <button data-testid="login-submit-button" disabled={busy} className="w-full bg-blue-900 hover:bg-slate-900 text-white font-semibold py-2.5 rounded-md flex items-center justify-center gap-2 transition-colors disabled:opacity-60">
            <Lock className="h-4 w-4" /> {busy ? "Memproses..." : "Masuk"}
          </button>
          <div className="flex items-center gap-2 text-xs text-slate-500"><ShieldCheck className="h-4 w-4 text-emerald-600" /> Sesi terenkripsi, 5x gagal login = kunci 15 menit</div>
        </form>
      </div>
    </div>
  );
}
