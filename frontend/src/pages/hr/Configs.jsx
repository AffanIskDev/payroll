import { useEffect, useState } from "react";
import { Save, RefreshCw, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PageTitle, Panel, Btn } from "@/components/common";

// Why the slip would print without a signature (signer.status in the backend)
const SIGNER_MISSING = {
  tanpa_penandatangan: "Belum ada penandatangan slip gaji untuk perusahaan ini di ROSY.",
  belum_ada_ttd: "Penandatangan ini belum punya gambar tanda tangan di ROSY.",
  belum_terambil: "Gambar tanda tangan belum terambil dari ROSY.",
};

const wib = (iso) => new Date(iso).toLocaleString("id-ID", {
  timeZone: "Asia/Jakarta", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
}) + " WIB";

// Penandatangan slip = Document Signer payroll di ROSY (permintaan user 11 Okt 2026): hanya ditampilkan di sini,
// dikelola di ROSY; gambar ini yang tercetak di Preview PDF Slip dan slip yang di-approve
function SignerPanel() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/hr/signer").then((r) => setS(r.data)).catch((e) => toast.error(errMsg(e))); }, []);

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api.post("/hr/signer/refresh");
      setS(r.data);
      if (r.data.status === "ada") toast.success("Penandatangan & tanda tangan diambil dari ROSY");
      else toast.warning(SIGNER_MISSING[r.data.status]);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const sg = s?.signer;
  return (
    <Panel title="Penandatangan Slip Gaji" className="mb-6" right={
      <Btn variant="outline" data-testid="signer-refresh-button" disabled={busy || !s || s.source !== "live"} onClick={refresh}>
        <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> {busy ? "Mengambil..." : "Ambil dari ROSY"}
      </Btn>}>
      {!s ? <div className="px-5 py-4 text-sm text-slate-500">Memuat...</div> : (
        <div className="flex flex-col sm:flex-row gap-5 px-5 py-4" data-testid="signer-panel">
          <div className="sm:w-60 h-32 shrink-0 border border-dashed border-slate-300 rounded-md bg-white flex items-center justify-center p-2">
            {s.image
              ? <img src={s.image} alt={`Tanda tangan ${sg?.nama || ""}`} className="max-h-full max-w-full object-contain" data-testid="signer-image" />
              : <span className="text-xs text-slate-400 text-center">Tidak ada gambar tanda tangan</span>}
          </div>
          <div className="text-sm space-y-1 min-w-0">
            <div className="font-semibold text-slate-900" data-testid="signer-name">{sg ? sg.nama : "Belum ada penandatangan"}</div>
            {sg && <div className="text-slate-600">{sg.jabatan}{s.company?.nama ? ` · ${s.company.nama}` : ""}</div>}
            {s.status !== "ada" && (
              <div className="!mt-3 flex gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-xs" data-testid="signer-warning">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{SIGNER_MISSING[s.status]}{s.error ? ` (${s.error})` : ""} Slip yang di-approve sekarang terbit <b>tanpa tanda tangan</b>.</span>
              </div>
            )}
            <p className="!mt-3 text-xs text-slate-500">Sama dengan slip ROSY: diambil dari ROSY HRD, menu Penandatangan Dokumen (konteks payroll), dan ikut tercetak di Preview PDF Slip. Untuk mengganti penandatangan atau tanda tangannya, ubah di ROSY lalu klik <b>Ambil dari ROSY</b>. Slip yang sudah di-approve tidak berubah.</p>
            {s.fetched_at && <p className="text-xs text-slate-400" data-testid="signer-fetched-at">Terakhir diambil: {wib(s.fetched_at)}</p>}
          </div>
        </div>
      )}
    </Panel>
  );
}

// Dasar PPh 21 (permintaan user 13 Okt 2026): satu setelan global (backend engine.pph21_basis); rumusnya sama dengan
// baris "Bruto Objek Pajak" di halaman review slip. Hanya Potongan Presensi & Absensi yang membedakan keduanya.
const PPH21_BASIS = {
  bersih: {
    title: "Pendapatan bersih", tag: "bawaan",
    formula: "Total Pendapatan − Potongan Presensi & Absensi − JHT & JP perusahaan",
    note: "PPh 21 dihitung dari penghasilan setelah potongan kehadiran, jadi karyawan yang terpotong dikenai pajak lebih kecil.",
  },
  kotor: {
    title: "Pendapatan kotor",
    formula: "Total Pendapatan − JHT & JP perusahaan",
    note: "PPh 21 dihitung dari gaji & tunjangan penuh; potongan presensi & absensi tidak menurunkan dasar pajak.",
  },
};

function Pph21BasisPanel({ value, choices, onChange }) {
  return (
    <Panel title="Dasar PPh 21" className="mb-6">
      <div className="px-5 py-4" data-testid="pph21-basis-panel">
        <p className="text-xs text-slate-500 mb-3">Penghasilan yang dipakai sebagai dasar tarif TER (Jan–Nov) dan perhitungan setahun Pasal 17 (Desember). Take home pay hanya berubah lewat PPh 21-nya.</p>
        <div role="radiogroup" aria-label="Dasar PPh 21" className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {choices.filter((k) => PPH21_BASIS[k]).map((k) => {
            const o = PPH21_BASIS[k];
            const on = value === k;
            return (
              <label key={k} data-testid={`pph21-basis-${k}`} className={`flex gap-3 rounded-md border px-4 py-3 cursor-pointer transition-colors ${on ? "border-blue-900 ring-2 ring-blue-900/20 bg-blue-50/40" : "border-slate-200 hover:border-blue-400"}`}>
                <input type="radio" name="PPH21_BASIS" value={k} checked={on} onChange={() => onChange(k)} className="mt-1 h-4 w-4 accent-blue-900 shrink-0" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 min-h-[24px] text-sm font-semibold text-slate-900">{o.title}{o.tag && <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">{o.tag}</span>}</span>
                  <span className="block num text-xs text-slate-700 mt-1">{o.formula}</span>
                  <span className="block text-xs text-slate-500 mt-1">{o.note}</span>
                </span>
              </label>
            );
          })}
        </div>
        <p className="text-xs text-slate-500 mt-3">Berlaku untuk slip yang dihitung sesudah disimpan: klik <b>Fetch Data Terbaru</b> di halaman periode untuk periode yang masih draft. Slip yang sudah di-approve tidak berubah, dan 1721-A1 mengikuti dasar yang dipakai tiap slipnya.</p>
      </div>
    </Panel>
  );
}

export default function Configs() {
  const [list, setList] = useState([]);
  const [vals, setVals] = useState({});
  const load = () => api.get("/hr/configs").then((r) => {
    setList(r.data);
    setVals(Object.fromEntries(r.data.map((c) => [c.config_key, c.config_value])));
  });
  useEffect(() => { load(); }, []);
  const basis = list.find((c) => c.config_key === "PPH21_BASIS" && c.choices?.length); // none until the backend has seeded it

  const save = async () => {
    try {
      await api.put("/hr/configs", vals);
      toast.success("Konfigurasi disimpan. Proses ulang payroll untuk menerapkan.");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="max-w-3xl">
      <PageTitle title="Konfigurasi Payroll" subtitle="payroll_configs — parameter global">
        <Btn data-testid="save-config-button" onClick={save}><Save className="h-4 w-4" /> Simpan</Btn>
      </PageTitle>
      <SignerPanel />
      {basis && <Pph21BasisPanel value={vals.PPH21_BASIS} choices={basis.choices} onChange={(v) => setVals({ ...vals, PPH21_BASIS: v })} />}
      <Panel>
        <div className="divide-y divide-slate-100">
          {list.filter((c) => c.config_key !== "PPH21_BASIS").map((c) => (
            <div key={c.config_key} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-5 py-4">
              <div>
                <div className="num text-sm font-semibold">{c.config_key}</div>
                <div className="text-xs text-slate-500">{c.description}</div>
              </div>
              <input data-testid={`config-${c.config_key}`} value={vals[c.config_key] ?? ""} onChange={(e) => setVals({ ...vals, [c.config_key]: e.target.value })} className="num border border-slate-300 rounded-md px-3 py-2 text-sm text-right w-full sm:w-48" />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
