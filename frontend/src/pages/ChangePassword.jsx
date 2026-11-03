import { useState } from "react";
import { toast } from "sonner";
import { KeyRound } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";

// Layar wajib ganti kata sandi: kata sandi sementara dari Manager (daftar pengguna RUSA) hanya boleh dipakai sekali masuk.
export default function ChangePassword() {
  const { user, logout, refresh } = useAuth();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const field = "w-full h-12 border border-slate-300 rounded-xl px-4 text-base outline-none focus:border-brand-700 focus:ring-4 focus:ring-brand-100";

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Kata sandi baru dan pengulangannya tidak sama");
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current_password: cur, new_password: pw });
      toast.success("Kata sandi diganti");
      await refresh();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center p-6 bg-white" data-testid="change-password-screen">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5">
        <div className="space-y-1.5">
          <div className="h-11 w-11 rounded-xl bg-brand-700 text-white grid place-items-center"><KeyRound className="h-5 w-5" /></div>
          <h1 className="text-2xl font-extrabold text-slate-900">Ganti kata sandi</h1>
          <p className="text-sm text-slate-600">Halo {user?.name}. Kata sandi Anda dibuatkan sementara oleh Manager HRD — buat kata sandi sendiri sebelum memakai RUSA. Minimal 10 karakter, memuat huruf dan angka.</p>
        </div>
        <div className="space-y-2"><label className="block text-sm font-bold text-slate-900" htmlFor="cp-cur">Kata sandi sementara</label>
          <input id="cp-cur" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required className={field} data-testid="cp-current" /></div>
        <div className="space-y-2"><label className="block text-sm font-bold text-slate-900" htmlFor="cp-new">Kata sandi baru</label>
          <input id="cp-new" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required className={field} data-testid="cp-new" /></div>
        <div className="space-y-2"><label className="block text-sm font-bold text-slate-900" htmlFor="cp-new2">Ulangi kata sandi baru</label>
          <input id="cp-new2" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required className={field} data-testid="cp-new2" /></div>
        <button disabled={busy} className="w-full h-12 bg-brand-700 hover:bg-brand-800 text-white text-base font-bold rounded-xl transition-colors disabled:opacity-60" data-testid="cp-submit">{busy ? "Menyimpan..." : "Simpan kata sandi"}</button>
        <button type="button" onClick={logout} className="w-full text-sm font-semibold text-slate-500 hover:text-slate-800">Keluar</button>
      </form>
    </div>
  );
}
