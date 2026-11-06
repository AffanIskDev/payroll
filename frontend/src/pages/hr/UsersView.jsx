import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, KeyRound, Copy, Building2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";
import { ROLE_LABELS, useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Pengguna RUSA (user 3 Nov 2026): siapa boleh memakai RUSA dan sebagai apa diatur di sini oleh Master Admin, terpisah dari ROSY.
// Multi-PT (6 Nov 2026): akses PER PERUSAHAAN — tiap PT dicentang dengan perannya sendiri (Manager HRD menyetujui, Supervisor
// menyiapkan & mengajukan), atau "Semua PT" (termasuk PT yang ditambahkan kemudian). PT utama = PT yang dibuka saat login.
// Kata sandi: "RUSA" (disimpan di RUSA, sementara dari Master Admin lalu wajib diganti) atau "ROSY" (diperiksa ke ROSY).
const INPUT = "w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:border-brand-400 focus:ring-2 focus:ring-brand-700/10 outline-none";
const AUTH = { local: "Kata sandi RUSA", rosy: "Kata sandi ROSY" };
const HR_ROLE_LABELS = { manager_hrd: "Manager HRD", supervisor: "Supervisor HRD" };

/** Ringkasan akses untuk tabel: "Semua PT · Manager HRD" atau daftar "RUMI · Supervisor HRD". */
function AksesBadges({ u, companies }) {
  if (u.role === "master_admin") return <span className="text-xs text-slate-500">Mengatur pengguna (tanpa data gaji)</span>;
  const nama = Object.fromEntries(companies.map((c) => [c.id, c.nama]));
  const items = u.semua_pt ? [{ label: "Semua PT", role: u.role }] : (u.akses || []).map((a) => ({ label: nama[a.company_id] || a.company_id, role: a.role, id: a.company_id }));
  if (!items.length) return <span className="text-xs font-semibold text-amber-700">Belum ada akses</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((it) => (
        <span key={it.label} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${it.role === "manager_hrd" ? "bg-brand-50 text-brand-800" : "bg-slate-100 text-slate-700"}`}>
          {it.label} · {HR_ROLE_LABELS[it.role] || it.role}{it.id && it.id === u.pt_utama && <span title="PT utama">★</span>}
        </span>
      ))}
    </div>
  );
}

const kosong = (companies) => ({
  mode: "add", username: "", name: "", jenis: "hr", auth_mode: "local", semua_pt: false, role_semua: "manager_hrd",
  akses: Object.fromEntries(companies.map((c) => [c.id, ""])), pt_utama: "",
});

const dariPengguna = (u, companies) => ({
  mode: "edit", id: u.id, username: u.username, name: u.name, jenis: u.role === "master_admin" ? "admin" : "hr",
  auth_mode: u.auth_mode, semua_pt: !!u.semua_pt, role_semua: u.role === "supervisor" ? "supervisor" : "manager_hrd",
  akses: Object.fromEntries(companies.map((c) => [c.id, (u.akses || []).find((a) => a.company_id === c.id)?.role || ""])),
  pt_utama: u.pt_utama || "",
});

/** Isi form → badan permintaan API. */
function payload(f) {
  if (f.jenis === "admin") return { name: f.name, role: "master_admin", akses: [], semua_pt: false, pt_utama: null };
  const akses = Object.entries(f.akses).filter(([, r]) => r).map(([company_id, role]) => ({ company_id, role }));
  // peran bawaan pengguna: dipakai untuk "Semua PT"; selain itu peran tertinggi di PT-PT-nya
  const role = f.semua_pt ? f.role_semua : (akses.some((a) => a.role === "manager_hrd") ? "manager_hrd" : "supervisor");
  return { name: f.name, role, semua_pt: f.semua_pt, akses: f.semua_pt ? [] : akses, pt_utama: f.pt_utama || null };
}

export default function UsersView() {
  const { user: me } = useAuth();
  const [data, setData] = useState({ users: [], companies: [], rosy_available: false });
  const [form, setForm] = useState(null);       // null = tertutup
  const [temp, setTemp] = useState(null);       // {username, password}: kata sandi sementara, hanya tampil sekali
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = () => api.get("/hr/users").then((r) => setData(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const companies = data.companies || [];

  const save = async () => {
    setBusy(true); setError("");
    try {
      const body = payload(form);
      const { data: r } = form.mode === "add"
        ? await api.post("/hr/users", { ...body, username: form.username, auth_mode: form.auth_mode })
        : await api.put(`/hr/users/${form.id}`, body);
      setForm(null); load();
      if (r.temp_password) setTemp({ username: r.user.username, password: r.temp_password });
      else toast.success(form.mode === "add" ? `${r.user.name} ditambahkan` : "Akses diperbarui");
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
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const setAkses = (id, role) => setForm((f) => ({ ...f, akses: { ...f.akses, [id]: role } }));
  const ptDipilih = form ? (form.semua_pt ? companies.map((c) => c.id) : Object.entries(form.akses).filter(([, r]) => r).map(([id]) => id)) : [];
  const self = form?.mode === "edit" && form.id === me?.id;

  return (
    <div>
      <PageTitle title="Pengguna RUSA" subtitle="Siapa yang boleh memakai RUSA, di perusahaan mana, dan sebagai apa — diatur oleh Master Admin, terpisah dari ROSY">
        <Btn onClick={() => { setError(""); setForm(kosong(companies)); }} data-testid="user-add-button"><Plus className="h-4 w-4" /> Tambah Pengguna</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]" data-testid="users-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>{["Pengguna", "Akses Perusahaan", "Kata Sandi", "Status", "Login Terakhir", ""].map((h) => <th key={h} className="px-3 py-3 text-left font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.users.map((u) => {
                const diri = u.id === me?.id;
                return (
                  <tr key={u.id} className={u.is_active === false ? "opacity-60" : ""} data-testid={`user-row-${u.username}`}>
                    <td className="px-3 py-2.5"><div className="font-semibold text-slate-900">{u.name}{diri && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-600">Anda</span>}</div>
                      <div className="text-xs text-slate-500">{u.username}{u.role === "master_admin" && " · Master Admin"}</div></td>
                    <td className="px-3 py-2.5" data-testid={`user-akses-${u.username}`}><AksesBadges u={u} companies={companies} /></td>
                    <td className="px-3 py-2.5 text-xs text-slate-600">{AUTH[u.auth_mode]}{u.must_change_password && <div className="text-amber-700 font-semibold">Belum diganti</div>}</td>
                    <td className="px-3 py-2.5 text-xs"><span className={`inline-flex items-center gap-1.5 font-medium ${u.is_active === false ? "text-slate-500" : "text-emerald-700"}`}><span className={`h-2 w-2 rounded-full ${u.is_active === false ? "bg-slate-400" : "bg-emerald-500"}`} />{u.is_active === false ? "Nonaktif" : "Aktif"}</span></td>
                    <td className="px-3 py-2.5 text-xs text-slate-500 whitespace-nowrap">{u.last_login_at ? formatDateTime(u.last_login_at) : "Belum pernah"}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <Btn variant="ghost" onClick={() => { setError(""); setForm(dariPengguna(u, companies)); }} data-testid={`user-edit-${u.username}`}><Building2 className="h-4 w-4" /> Atur akses</Btn>
                      {u.auth_mode === "local" && !diri && <Btn variant="ghost" onClick={() => reset(u)} data-testid={`user-reset-${u.username}`}><KeyRound className="h-4 w-4" /> Reset sandi</Btn>}
                      {!diri && <Btn variant="ghost" className={u.is_active === false ? "" : "!text-rose-600 hover:!bg-rose-50"} data-testid={`user-toggle-${u.username}`}
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
        <DialogContent data-testid="user-form-dialog" className="max-w-lg">
          <DialogHeader><DialogTitle>{form?.mode === "add" ? "Tambah Pengguna" : `Atur Akses — ${form?.name}`}</DialogTitle>
            <DialogDescription>Manager HRD menyetujui & mengunci gaji; Supervisor HRD menyiapkan dan mengajukan. Peran bisa berbeda di tiap perusahaan.</DialogDescription></DialogHeader>
          {form && (
            <div className="grid gap-3">
              {form.mode === "add" && <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Username *</span><input className={INPUT} value={form.username} onChange={set("username")} data-testid="user-form-username" autoComplete="off" /></label>}
              <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Nama *</span><input className={INPUT} value={form.name} onChange={set("name")} data-testid="user-form-name" /></label>
              <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Jenis akun</span>
                <select className={INPUT} value={form.jenis} onChange={set("jenis")} disabled={self} data-testid="user-form-jenis">
                  <option value="hr">Pengguna payroll (Manager / Supervisor HRD)</option>
                  <option value="admin">Master Admin — hanya mengatur pengguna, tanpa akses data gaji</option>
                </select></label>

              {form.jenis === "hr" && (
                <div className="rounded-lg border border-slate-200 p-3 grid gap-2" data-testid="user-form-akses">
                  <div className="text-xs font-semibold text-slate-600">Akses perusahaan *</div>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.semua_pt} onChange={set("semua_pt")} data-testid="user-form-semua-pt" />
                    <span className="font-semibold">Semua PT</span><span className="text-xs text-slate-500">(termasuk PT yang ditambahkan nanti)</span>
                    {form.semua_pt && <select className={INPUT + " !w-auto ml-auto"} value={form.role_semua} onChange={set("role_semua")} data-testid="user-form-role-semua">
                      {Object.entries(HR_ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
                  </label>
                  {!form.semua_pt && companies.map((c) => (
                    <div key={c.id} className="flex items-center gap-2 text-sm" data-testid={`user-form-pt-${c.id}`}>
                      <input type="checkbox" checked={!!form.akses[c.id]} onChange={(e) => setAkses(c.id, e.target.checked ? "supervisor" : "")} />
                      <span className="flex-1">{c.nama} <span className="text-xs text-slate-500">{c.nama_legal}</span></span>
                      {form.akses[c.id] && <select className={INPUT + " !w-auto"} value={form.akses[c.id]} onChange={(e) => setAkses(c.id, e.target.value)}>
                        {Object.entries(HR_ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
                    </div>
                  ))}
                  {ptDipilih.length > 1 && (
                    <label className="text-sm mt-1"><span className="mb-1 block text-xs font-semibold text-slate-600">PT utama (dibuka saat login)</span>
                      <select className={INPUT} value={ptDipilih.includes(form.pt_utama) ? form.pt_utama : ""} onChange={set("pt_utama")} data-testid="user-form-pt-utama">
                        <option value="">Otomatis (urutan pertama)</option>
                        {companies.filter((c) => ptDipilih.includes(c.id)).map((c) => <option key={c.id} value={c.id}>{c.nama}</option>)}
                      </select></label>
                  )}
                </div>
              )}

              {form.mode === "add" && <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-600">Kata sandi</span>
                <select className={INPUT} value={form.auth_mode} onChange={set("auth_mode")} data-testid="user-form-auth">
                  <option value="local">Kata sandi RUSA — dibuatkan sementara, diganti saat login pertama</option>
                  {data.rosy_available && <option value="rosy">Kata sandi ROSY — username harus sama dengan username ROSY</option>}
                </select></label>}
              {error && <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" data-testid="user-form-error">{error}</div>}
              <div className="flex justify-end gap-2"><Btn variant="outline" disabled={busy} onClick={() => setForm(null)}>Batal</Btn><Btn disabled={busy} onClick={save} data-testid="user-form-save">{busy ? "Menyimpan..." : form.mode === "add" ? "Tambah" : "Simpan"}</Btn></div>
            </div>
          )}
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
