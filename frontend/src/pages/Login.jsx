import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Eye, EyeOff, ShieldCheck, ArrowBigUp } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";

// Tampilan login mengikuti pola halaman login ROSY baru (desain RUMAT, Okt 2026): panel brand di kiri, form di kanan,
// satu kolom di HP/tablet. Logika login tidak berubah.
export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(username, password);
      nav("/hr-manager");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full h-12 border border-slate-300 rounded-xl px-4 text-base outline-none focus:border-brand-700 focus:ring-4 focus:ring-brand-100";

  return (
    <div className="min-h-screen grid grid-rows-[auto_1fr] lg:grid-rows-1 lg:grid-cols-[minmax(0,560px)_1fr] bg-white">
      <div className="bg-brand-700 text-white px-6 py-8 sm:px-10 lg:p-14 flex flex-col gap-8 lg:justify-between">
        <div className="flex items-center gap-3">
          {/* [LOGO RUMAT] ganti ikon ini dengan logo resmi bila sudah ada */}
          <div className="h-11 w-11 rounded-xl bg-white text-brand-700 grid place-items-center"><Building2 className="h-5 w-5" /></div>
          <div>
            <div className="text-xl font-extrabold tracking-[0.12em]">RASA</div>
            <div className="text-sm text-brand-100">Aplikasi Penggajian RUMAT</div>
          </div>
        </div>
        <div className="space-y-4 fade-up hidden sm:block">
          <div className="text-sm font-bold uppercase tracking-[0.14em] text-brand-200">Bagian dari ekosistem ROSY</div>
          <h1 className="text-3xl xl:text-4xl font-extrabold leading-tight">Gaji tim RUMAT, dihitung tepat dan tepat waktu.</h1>
          <p className="text-brand-100 max-w-md text-base leading-relaxed">Data karyawan, presensi, dan lembur langsung dari ROSY. Slip gaji terkirim ke RUMATku dalam PDF terlindungi sandi.</p>
        </div>
        <div className="hidden lg:block text-xs text-brand-200">PP 35/2021 · PP 58/2023 · PMK 168/2023 · UU HPP 7/2021</div>
      </div>
      <div className="flex flex-col p-6 sm:p-10">
        <div className="flex-1 flex items-center justify-center">
          <form onSubmit={submit} className="w-full max-w-sm space-y-5 fade-up" data-testid="login-form">
            <div className="space-y-1.5">
              <h2 className="text-3xl font-extrabold text-slate-900">Masuk ke RASA</h2>
              <p className="text-base text-slate-600">Gunakan akun ROSY Anda. Khusus Manager HRD dan Supervisor HRD.</p>
            </div>
            <div className="space-y-2">
              <label htmlFor="login-username" className="block text-sm font-bold text-slate-900">Username ROSY</label>
              <input id="login-username" data-testid="login-username-input" value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" autoFocus className={field} placeholder="username ROSY" />
            </div>
            <div className="space-y-2">
              <label htmlFor="login-password" className="block text-sm font-bold text-slate-900">Kata sandi</label>
              <div className="relative">
                <input id="login-password" data-testid="login-password-input" type={show ? "text" : "password"} autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} onKeyUp={(e) => setCaps(e.getModifierState?.("CapsLock"))} required className={`${field} pr-14`} />
                <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"} data-testid="login-toggle-password"
                  className="absolute right-1 top-1 h-10 w-11 grid place-items-center rounded-lg text-slate-500 hover:bg-slate-100">
                  {show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
              {caps && <div className="flex items-center gap-1.5 text-sm font-semibold text-amber-700" data-testid="login-capslock"><ArrowBigUp className="h-4 w-4" /> Caps Lock aktif</div>}
            </div>
            <button data-testid="login-submit-button" disabled={busy} className="w-full h-12 bg-brand-700 hover:bg-brand-800 text-white text-base font-bold rounded-xl transition-colors disabled:opacity-60">
              {busy ? "Memproses..." : "Masuk"}
            </button>
            <div className="flex items-start gap-2 text-sm text-slate-600"><ShieldCheck className="h-4 w-4 mt-0.5 shrink-0 text-brand-600" /> Kata sandi diperiksa langsung ke ROSY dan tidak disimpan di RASA. Setelah 5 kali gagal, akun dikunci 15 menit.</div>
          </form>
        </div>
        <div className="text-center text-xs text-slate-500 pt-6">© 2026 PT Rumah Perawatan Indonesia · RASA</div>
      </div>
    </div>
  );
}
