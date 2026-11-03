import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, KeyRound, Copy } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";
import { ROLE_LABELS, useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Pengguna RUSA (user 3 Nov 2026): siapa boleh memakai RUSA dan sebagai apa diatur di sini oleh Manager HRD, terpisah dari ROSY.
// Kata sandi: "RUSA" (disimpan di RUSA, sementara dari Manager lalu wajib diganti) atau "ROSY" (diperiksa ke ROSY).
const INPUT = "w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:border-brand-400 focus:ring-2 focus:ring-brand-700/10 outline-none";
const AUTH = { local: "Kata sandi RUSA", rosy: "Kata sandi ROSY" };

export default function UsersView() {
  const { user: me } = useAuth();
  const [data, setData] = useState({ users: [], rosy_available: false, company: "" });
  const [form, setForm] = useState(null);       // null = tertutup; {} = tambah
  const [temp, setTemp] = useState(null);       // {username, password}: kata sandi sementara, hanya tampil sekali
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = () => api.get("/hr/users").then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const open = () => { setError(""); setForm({ username: "", name: "", role: "supervisor", auth_mode: "local" }); };
  const add = async () => {
    setBusy(true); setError("");
    try {
      const { data: r } = await api.post("/hr/users", form);
      setForm(null); load();
      if (r.temp_password) setTemp({ username: r.user.username, password: r.temp_password });
      else toast.success(`${r.user.name} ditambahkan`);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const patch = async (u, body, okMsg) => {
    try {
      const { data: r } = await api.put(`/hr/users/${u.id}`, body);
      toast.success(okMsg); load();
      if (r.temp_password) setTemp({ username: u.username, password: r.temp_password });
    } catch (e) { toast.error(errMsg(e)); }
  };
  const reset = async (u) => {
    if (!window.confirm(`Buat kata sandi sementara baru untuk ${u.name}? Kata sandi lamanya langsung tidak berlaku.`)) return;
    try { const { data: r } = await api.post(`/hr/users/${u.id}/reset-password`); setTemp({ username: u.username, password: r.temp_password }); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const copy = () => navigator.clipboard?.writeText(temp.password).then(() => toast.success("Disalin"));
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div>
      <PageTitle title="Pengguna RUSA" subtitle={`Siapa yang boleh memakai RUSA ${data.company ? `(${data.company})` : ""} dan sebagai apa — diatur oleh Master Admin, terpisah dari ROSY`}>
        <Btn onClick={open} data-testid="user-add-button"><Plus className="h-4 w-4" /> Tambah Pengguna</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]" data-testid="users-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>{["Pengguna", "Peran", "Kata Sandi", "Status", "Login Terakhir", ""].map((h) => <th key={h} className="px-3 py-3 text-left font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.users.map((u) => {
                const self = u.id === me?.id;
                return (
                  <tr key={u.id} className={u.is_active === false ? "opacity-60" : ""} data-testid={`user-row-${u.username}`}>
                    <td className="px-3 py-2.5"><div className="font-semibold text-slate-900">{u.name}{self && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-600">Anda</span>}</div><div className="text-xs text-slate-500">{u.username}</div></td>
                    <td className="px-3 py-2.5">
                      <select className={INPUT + " !w-auto"} value={u.role} disabled={self} title={self ? "Peran akun sendiri tidak bisa diubah" : ""} data-testid={`user-role-${u.username}`}
                        onChange={(e) => patch(u, { role: e.target.value }, "Peran diperbarui")}>
                        {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-600">{AUTH[u.auth_mode]}{u.must_change_password && <div className="text-amber-700 font-semibold">Belum diganti</div>}</td>
                    <td className="px-3 py-2.5 text-xs"><span className={`inline-flex items-center gap-1.5 font-medium ${u.is_active === false ? "text-slate-500" : "text-emerald-700"}`}><span className={`h-2 w-2 rounded-full ${u.is_active === false ? "bg-slate-400" : "bg-emerald-500"}`} />{u.is_active === false ? "Nonaktif" : "Aktif"}</span></td>
                    <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{u.last_login_at ? formatDateTime(u.last_login_at) : "Belum pernah"}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {u.auth_mode === "local" && <Btn variant="ghost" onClick={() => reset(u)} data-testid={`user-reset-${u.username}`}><KeyRound className="h-4 w-4" /> Reset sandi</Btn>}
                      {!self && <Btn variant="ghost" className={u.is_active === false ? "" : "!text-rose-600 hover:!bg-rose-50"} data-testid={`user-toggle-${u.username}`}
                        onClick={() => patch(u, { is_active: u.is_active === false }, u.is_active === false ? "Pengguna diaktifkan" : "Pengguna dinonaktifkan")}>{u.is_active === false ? "Aktifkan" : "Nonaktifkan"}</Btn>}
                    </td>
                  </tr>
                );
              })}
              {!data.users.length && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">Belum ada pengguna.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      <Dialog open={!!form} onOpenChange={(o) => !busy && !o && setForm(null)}>
        <DialogContent data-testid="user-form-dialog">
          <DialogHeader><DialogTitle>Tambah Pengguna</DialogTitle>
            <DialogDescription>Orang yang ditunjuk memakai RUSA perusahaan ini. Manager menyetujui & mengunci gaji; Supervisor menyiapkan dan mengajukan; Master Admin hanya mengatur pengguna (tanpa akses data gaji).</DialogDescription></DialogHeader>
          <div className="grid gap-3">
            <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Username *</span><input className={INPUT} value={form?.username || ""} onChange={set("username")} data-testid="user-form-username" autoComplete="off" /></label>
            <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Nama *</span><input className={INPUT} value={form?.name || ""} onChange={set("name")} data-testid="user-form-name" /></label>
            <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Peran *</span>
              <select className={INPUT} value={form?.role || "supervisor"} onChange={set("role")} data-testid="user-form-role">{Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Kata sandi</span>
              <select className={INPUT} value={form?.auth_mode || "local"} onChange={set("auth_mode")} data-testid="user-form-auth">
                <option value="local">Kata sandi RUSA — dibuatkan sementara, diganti saat login pertama</option>
                {data.rosy_available && <option value="rosy">Kata sandi ROSY — username harus sama dengan username ROSY</option>}
              </select></label>
            {error && <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" data-testid="user-form-error">{error}</div>}
            <div className="flex justify-end gap-2"><Btn variant="outline" disabled={busy} onClick={() => setForm(null)}>Batal</Btn><Btn disabled={busy} onClick={add} data-testid="user-form-save">{busy ? "Menyimpan..." : "Tambah"}</Btn></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!temp} onOpenChange={(o) => !o && setTemp(null)}>
        <DialogContent data-testid="temp-password-dialog">
          <DialogHeader><DialogTitle>Kata sandi sementara</DialogTitle>
            <DialogDescription>Berikan ke <b>{temp?.username}</b> lewat jalur aman. Kata sandi ini <b>hanya tampil sekali</b> dan harus diganti saat login pertama.</DialogDescription></DialogHeader>
          <div className="flex items-center gap-2 rounded-md border border-slate-300 bg-slate-50 px-3 py-3">
            <code className="flex-1 text-lg font-bold tracking-wider text-slate-900 select-all" data-testid="temp-password-value">{temp?.password}</code>
            <Btn variant="outline" onClick={copy}><Copy className="h-4 w-4" /> Salin</Btn>
          </div>
          <div className="flex justify-end"><Btn onClick={() => setTemp(null)} data-testid="temp-password-close">Sudah saya catat</Btn></div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
