import { useEffect, useMemo, useState } from "react";
import { Save, Search } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, formatDateTime } from "@/lib/format";
import { Btn } from "@/components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Tambahan Bulanan diinput di RUSA (18 Nov 2026) untuk PT dengan Sumber Gaji = RUSA: pengganti Tambahan Bulanan ROSY
// (Bonus, Transport Homecare, Potongan Tidak Mencapai Target, Cicilan / Pinjaman) untuk periode gaji ini. Disimpan lalu slip
// draft karyawan yang berubah langsung dihitung ulang (backend tambahan_rusa.py). THR & Bonus Tahunan diisi di run-nya sendiri.
const angka = (v) => (!v ? "" : Math.round(Number(v)).toLocaleString("id-ID"));
const bacaAngka = (s) => Number(String(s).replace(/[^\d]/g, "")) || 0;

export default function TambahanBulananDialog({ open, pid, onClose, onSaved }) {
  const [d, setD] = useState(null);
  const [nilai, setNilai] = useState({});
  const [q, setQ] = useState("");
  const [catatan, setCatatan] = useState("");
  const [busy, setBusy] = useState(false);
  const [riwayat, setRiwayat] = useState(null);

  const terima = (data) => {
    setD(data);
    setNilai(Object.fromEntries(data.rows.map((r) => [r.id, { ...r.nilai }])));
  };
  useEffect(() => {
    if (!open) return;
    setD(null); setQ(""); setCatatan(""); setRiwayat(null);
    api.get(`/hr/tambahan-bulanan/${pid}`).then((r) => terima(r.data)).catch((e) => { toast.error(errMsg(e)); onClose(); });
  }, [open, pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const asal = useMemo(() => Object.fromEntries((d?.rows || []).map((r) => [r.id, r.nilai])), [d]);
  const berubah = useMemo(() => (d?.rows || []).flatMap((r) => d.kode
    .filter(({ kode }) => (nilai[r.id]?.[kode] || 0) !== (asal[r.id]?.[kode] || 0))
    .map(({ kode }) => ({ employee_id: r.id, kode, nominal: nilai[r.id]?.[kode] || 0 }))), [d, nilai, asal]);
  const rows = (d?.rows || []).filter((r) => `${r.nik} ${r.name} ${r.department}`.toLowerCase().includes(q.trim().toLowerCase()));
  const total = (kode) => (d?.rows || []).reduce((s, r) => s + (nilai[r.id]?.[kode] || 0), 0);

  const ubah = (eid, kode) => (e) => setNilai({ ...nilai, [eid]: { ...nilai[eid], [kode]: bacaAngka(e.target.value) } });
  const tutup = () => {
    if (berubah.length && !window.confirm(`${berubah.length} perubahan belum disimpan. Tutup tanpa menyimpan?`)) return;
    onClose();
  };
  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put(`/hr/tambahan-bulanan/${pid}`, { items: berubah, catatan });
      terima(r.data);
      setCatatan(""); setRiwayat(null);
      toast.success(`Tambahan Bulanan disimpan — slip ${r.data.diubah} karyawan dihitung ulang`);
      onSaved();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const lihatRiwayat = () => api.get(`/hr/tambahan-bulanan/${pid}/riwayat`).then((r) => setRiwayat(r.data)).catch((e) => toast.error(errMsg(e)));
  const label = Object.fromEntries((d?.kode || []).map((k) => [k.kode, k.label]));

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && !o && tutup()}>
      <DialogContent data-testid="tambahan-dialog" className="max-w-6xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Tambahan Bulanan — {d?.period?.period_name || "…"}</DialogTitle>
          <DialogDescription>
            Pengganti Tambahan Bulanan ROSY untuk perusahaan ini (Sumber Gaji = RUSA). Slip draft karyawan yang diubah langsung dihitung ulang. THR & Bonus Tahunan diisi di menu Payroll → THR / Bonus Tahunan.
          </DialogDescription>
        </DialogHeader>
        {!d ? <div className="py-8 text-center text-sm text-slate-500">Memuat…</div> : (
          <div className="grid gap-3">
            {!d.bisa_ubah && (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="tambahan-hanya-lihat">
                {d.sumber !== "rusa" ? "Sumber Gaji perusahaan ini ROSY: Tambahan Bulanan diisi di ROSY." : "Periode sedang direview Manager atau sudah dikunci — hanya bisa dilihat."}
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2 border border-slate-300 rounded-md px-3 py-2 bg-white w-full sm:w-64">
                <Search className="h-4 w-4 text-slate-400" />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama / NIK / dept" className="outline-none text-sm w-full bg-transparent" data-testid="tambahan-cari" />
              </label>
              <div className="text-xs text-slate-500">{d.kode.map((k) => <div key={k.kode}><b className={k.jenis === "potongan" ? "text-rose-700" : "text-slate-700"}>{k.label}</b>: {k.keterangan}</div>)}</div>
            </div>
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-[13px]" data-testid="tambahan-tabel">
                <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-2.5 py-2.5 text-left font-semibold">Karyawan</th>
                    {d.kode.map((k) => <th key={k.kode} className={`px-2.5 py-2.5 text-right font-semibold ${k.jenis === "potongan" ? "text-rose-600" : ""}`}>{k.label}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((r) => (
                    <tr key={r.id} data-testid={`tambahan-row-${r.nik}`}>
                      <td className="px-2.5 py-2 min-w-[12rem]">
                        <div className="font-semibold text-slate-900 leading-snug">{r.name}</div>
                        <div className="text-xs text-slate-500"><span className="num">{r.nik}</span> · {r.department}</div>
                      </td>
                      {d.kode.map(({ kode }) => {
                        const v = nilai[r.id]?.[kode] || 0;
                        const diubah = v !== (asal[r.id]?.[kode] || 0);
                        return (
                          <td key={kode} className="px-2 py-2">
                            <input inputMode="numeric" disabled={!d.bisa_ubah} value={angka(v)} onChange={ubah(r.id, kode)} placeholder="0"
                              className={`num w-32 rounded-md border px-2 py-1.5 text-right text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-700/10 disabled:bg-slate-50 ${diubah ? "border-amber-400 bg-amber-50" : "border-slate-300"}`}
                              data-testid={`tambahan-${r.nik}-${kode}`} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={d.kode.length + 1} className="px-4 py-6 text-center text-slate-500">{d.rows.length ? "Tidak ada yang cocok." : "Belum ada karyawan di periode ini — isi gaji di menu Karyawan lalu Fetch Data Terbaru."}</td></tr>}
                </tbody>
                <tfoot className="bg-slate-50 text-xs font-semibold text-slate-700">
                  <tr>
                    <td className="px-2.5 py-2">Total ({d.rows.length} karyawan)</td>
                    {d.kode.map(({ kode }) => <td key={kode} className="px-2.5 py-2 text-right num">{rp(total(kode))}</td>)}
                  </tr>
                </tfoot>
              </table>
            </div>
            {d.bisa_ubah && (
              <input value={catatan} onChange={(e) => setCatatan(e.target.value)} placeholder="Catatan perubahan (opsional), mis. bonus kinerja Q4" className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" data-testid="tambahan-catatan" />
            )}
            {riwayat && (
              <div className="rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 max-h-48 overflow-y-auto" data-testid="tambahan-riwayat">
                {!riwayat.length ? "Belum ada perubahan." : (
                  <ul className="grid gap-1">
                    {riwayat.map((h) => (
                      <li key={h.id}><span className="text-slate-500">{formatDateTime(h.at)}</span> · <b>{h.oleh}</b> · {h.name} · {label[h.kode] || h.kode}: <span className="num">{rp(h.sebelum)} → <b className="text-slate-800">{rp(h.sesudah)}</b></span>{h.catatan && <span className="text-slate-500"> — {h.catatan}</span>}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" onClick={lihatRiwayat} className="tap text-xs font-semibold text-brand-700 hover:underline" data-testid="tambahan-lihat-riwayat">Lihat riwayat perubahan</button>
              <div className="flex gap-2">
                <Btn variant="outline" onClick={tutup} disabled={busy}>Tutup</Btn>
                {d.bisa_ubah && <Btn onClick={save} disabled={busy || !berubah.length} data-testid="tambahan-simpan"><Save className="h-4 w-4" /> {busy ? "Menyimpan…" : `Simpan${berubah.length ? ` (${berubah.length})` : ""}`}</Btn>}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
