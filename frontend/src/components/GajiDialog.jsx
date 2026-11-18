import { useEffect, useState } from "react";
import { Copy, Save } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, formatDateTime } from "@/lib/format";
import { Btn } from "@/components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Input gaji di RUSA (18 Nov 2026) untuk PT yang Sumber Gaji-nya RUSA (Konfigurasi GAJI_SUMBER): isinya sama dengan Kontrak
// Gaji ROSY yang dibaca RUSA — gaji pokok, tunjangan jabatan, tunjangan kehadiran, tarif lembur, program BPJS & kelas JKK.
// Identitas (nama, PTKP, rekening, tanggal masuk/keluar) tetap dari ROSY. Berlaku untuk slip draft sesudah Fetch Data Terbaru.
const INPUT = "w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-700/10";
const NOMINAL = [
  ["basic_salary", "Gaji Pokok *"],
  ["position_allowance", "Tunjangan Jabatan"],
  ["monthly_attendance_allowance", "Tunjangan Kehadiran"],
  ["overtime_hourly_rate", "Rate Lembur (Rp / jam)"],
];
const PROGRAMS = [["kes", "BPJS Kesehatan"], ["jkk", "JKK"], ["jkm", "JKM"], ["jht", "JHT"], ["jp", "JP"]];
const persen = (r) => `${(r * 100).toLocaleString("id-ID", { maximumFractionDigits: 2 })}%`;
const angka = (v) => (v === "" || v == null ? "" : Math.round(Number(v)).toLocaleString("id-ID"));
const bacaAngka = (s) => Number(String(s).replace(/[^\d]/g, "")) || 0;

const kosong = () => ({ basic_salary: 0, position_allowance: 0, monthly_attendance_allowance: 0, overtime_hourly_rate: 0,
  bpjs_programs: { kes: true, jkk: true, jkm: true, jht: true, jp: true }, jkk_rate: 0.0024, catatan: "" });
const dari = (g) => ({ ...kosong(), ...Object.fromEntries(NOMINAL.map(([k]) => [k, g[k] || 0])),
  bpjs_programs: { ...g.bpjs_programs }, jkk_rate: g.jkk_rate || 0.0024 });

export default function GajiDialog({ employee, onClose, onSaved }) {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!employee) return;
    setInfo(null); setForm(null);
    api.get(`/hr/gaji-karyawan/${employee.id}`).then((r) => {
      setInfo(r.data);
      setForm(r.data.gaji ? dari(r.data.gaji) : kosong());
    }).catch((e) => { toast.error(errMsg(e)); onClose(); });
  }, [employee]); // eslint-disable-line react-hooks/exhaustive-deps

  const setNominal = (k) => (e) => setForm({ ...form, [k]: bacaAngka(e.target.value) });
  const setProgram = (p) => (e) => setForm({ ...form, bpjs_programs: { ...form.bpjs_programs, [p]: e.target.checked } });
  const total = form ? form.basic_salary + form.position_allowance + form.monthly_attendance_allowance : 0;

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put(`/hr/gaji-karyawan/${employee.id}`, form);
      toast.success(`Gaji ${employee.name} disimpan. Klik Fetch Data Terbaru di periode draft untuk menghitung ulang slipnya.`);
      onSaved(r.data);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!employee} onOpenChange={(o) => !busy && !o && onClose()}>
      <DialogContent data-testid="gaji-dialog" className="max-w-xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Atur Gaji — {employee?.name}</DialogTitle>
          <DialogDescription>
            {employee?.nik} · {employee?.department}{employee?.ptkp_status && <> · PTKP {employee.ptkp_status}</>}. Identitas, PTKP & rekening tetap dari ROSY; gaji di bawah ini diisi di RUSA.
          </DialogDescription>
        </DialogHeader>
        {!form ? <div className="py-8 text-center text-sm text-slate-500">Memuat…</div> : (
          <div className="grid gap-4">
            {info?.gaji_rosy && (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600" data-testid="gaji-rosy-ref">
                <span>Kontrak Gaji di ROSY: gaji pokok <b className="num text-slate-800">{rp(info.gaji_rosy.basic_salary)}</b>, tunj. jabatan <b className="num text-slate-800">{rp(info.gaji_rosy.position_allowance)}</b> — tidak dipakai selama sumber gaji PT ini RUSA.</span>
                <Btn variant="outline" className="!min-h-[32px] !px-2.5 !py-1 text-xs" onClick={() => setForm({ ...dari(info.gaji_rosy), catatan: form.catatan })} data-testid="gaji-salin-rosy"><Copy className="h-3.5 w-3.5" /> Salin dari ROSY</Btn>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {NOMINAL.map(([k, label]) => (
                <label key={k} className="text-sm">
                  <span className="mb-1 block text-xs font-semibold text-slate-600">{label}</span>
                  <div className="flex items-center rounded-md border border-slate-300 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-700/10">
                    <span className="pl-3 text-xs text-slate-400">Rp</span>
                    <input inputMode="numeric" value={angka(form[k])} onChange={setNominal(k)} className="num w-full bg-transparent px-2 py-2 text-right text-sm outline-none" data-testid={`gaji-${k}`} />
                  </div>
                </label>
              ))}
            </div>
            <div className="text-xs text-slate-500">Gaji tetap per bulan (pokok + jabatan + kehadiran): <b className="num text-slate-800">{rp(total)}</b></div>

            <div className="rounded-lg border border-slate-200 p-3" data-testid="gaji-bpjs">
              <div className="mb-2 text-xs font-semibold text-slate-600">Program BPJS yang diikuti</div>
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                {PROGRAMS.map(([p, label]) => (
                  <label key={p} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={!!form.bpjs_programs[p]} onChange={setProgram(p)} className="h-4 w-4 accent-brand-700" data-testid={`gaji-bpjs-${p}`} />{label}
                  </label>
                ))}
              </div>
              {form.bpjs_programs.jkk && (
                <label className="mt-3 flex items-center gap-2 text-sm">
                  <span className="text-xs font-semibold text-slate-600">Tarif JKK (kelas risiko)</span>
                  <select value={form.jkk_rate} onChange={(e) => setForm({ ...form, jkk_rate: Number(e.target.value) })} className={INPUT + " !w-auto"} data-testid="gaji-jkk-rate">
                    {(info?.jkk_rates || [0.0024]).map((r) => <option key={r} value={r}>{persen(r)}</option>)}
                  </select>
                </label>
              )}
              <p className="mt-2 text-xs text-slate-500">Dasar upah & tarif mengikuti Konfigurasi PT ini (Dasar BPJS Kesehatan / Ketenagakerjaan).</p>
            </div>

            <label className="text-sm">
              <span className="mb-1 block text-xs font-semibold text-slate-600">Catatan perubahan (opsional)</span>
              <input value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} placeholder="mis. kenaikan gaji per SK November" className={INPUT} data-testid="gaji-catatan" />
            </label>

            {info?.riwayat?.length > 0 && (
              <details className="rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600" data-testid="gaji-riwayat">
                <summary className="cursor-pointer font-semibold text-slate-700">Riwayat perubahan ({info.riwayat.length})</summary>
                <ul className="mt-2 grid gap-1.5">
                  {info.riwayat.map((h) => (
                    <li key={h.id}>
                      <span className="text-slate-500">{formatDateTime(h.at)}</span> · <b>{h.oleh}</b>: gaji pokok{" "}
                      {h.sebelum ? <span className="num">{rp(h.sebelum.basic_salary)} → </span> : "diisi "}
                      <span className="num font-semibold text-slate-800">{rp(h.sesudah.basic_salary)}</span>
                      {h.catatan && <span className="text-slate-500"> — {h.catatan}</span>}
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div className="flex justify-end gap-2">
              <Btn variant="outline" onClick={onClose} disabled={busy}>Batal</Btn>
              <Btn onClick={save} disabled={busy || form.basic_salary <= 0} data-testid="gaji-simpan"><Save className="h-4 w-4" /> Simpan Gaji</Btn>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
