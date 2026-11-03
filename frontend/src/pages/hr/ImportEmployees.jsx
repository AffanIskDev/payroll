import { useRef, useState } from "react";
import { toast } from "sonner";
import { FileDown, Upload, CheckCircle2 } from "lucide-react";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { PageTitle, Panel, Btn, FilterTab } from "@/components/common";
import EmployeeTabs from "@/components/EmployeeTabs";

// Import Karyawan & Gaji (user 3 Nov 2026), alurnya seperti import gaji di ROSY: unduh template → unggah → PRATINJAU (tak ada
// yang tersimpan) → proses. Pratinjau dan proses membaca berkas yang sama; baris Error dilewati, sisanya disimpan.
const ACTION = {
  baru: ["Baru", "text-emerald-700", "bg-emerald-500"],
  ubah: ["Ubah", "text-sky-700", "bg-sky-500"],
  sama: ["Tidak berubah", "text-slate-500", "bg-slate-300"],
  error: ["Error", "text-rose-700", "bg-rose-500"],
};

export default function ImportEmployees() {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [done, setDone] = useState(null);

  const template = () => saveFile("get", "/hr/employees/import/template", "Template-Karyawan-Gaji-RUSA.xlsx")
    .catch(async (e) => toast.error(await blobErrMsg(e)));

  const send = async (path, f) => {
    const fd = new FormData();
    fd.append("file", f);
    return (await api.post(path, fd)).data;
  };
  const pickFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true); setDone(null); setFilter("all");
    try { setPreview(await send("/hr/employees/import/preview", f)); setFile(f); }
    catch (err) { setPreview(null); setFile(null); toast.error(errMsg(err)); }
    finally { setBusy(false); }
  };
  const commit = async () => {
    const { summary } = preview;
    const n = summary.baru + summary.ubah;
    if (!window.confirm(`Simpan ${summary.baru} karyawan baru dan ${summary.ubah} perubahan?${summary.error ? ` ${summary.error} baris Error dilewati.` : ""}`)) return;
    setBusy(true);
    try {
      const r = await send("/hr/employees/import/commit", file);
      setDone(r); setPreview(null); setFile(null);
      toast.success(`${n} karyawan disimpan (${r.saved.baru} baru, ${r.saved.ubah} diubah)`);
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };

  const s = preview?.summary;
  const rows = (preview?.rows || []).filter((r) => filter === "all" || r.action === filter);
  return (
    <div>
      <PageTitle title="Import Karyawan & Gaji" subtitle="Untuk karyawan yang gajinya dikelola di RUSA (bukan dari ROSY)" />
      <EmployeeTabs />
      <Panel>
        <div className="px-4 sm:px-5 py-4 grid gap-4 md:grid-cols-3" data-testid="import-steps">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">1. Unduh template</div>
            <p className="mt-1 text-sm text-slate-600">Berisi karyawan RUSA saat ini, jadi mengubah gaji massal cukup edit lalu unggah. Belum ada data = satu baris contoh.</p>
            <Btn variant="outline" className="mt-2" onClick={template} data-testid="import-template-button"><FileDown className="h-4 w-4" /> Unduh Template</Btn>
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">2. Unggah & periksa</div>
            <p className="mt-1 text-sm text-slate-600">Pratinjau menunjukkan baris Baru, Ubah, dan Error. Belum ada yang tersimpan.</p>
            <Btn className="mt-2" disabled={busy} onClick={() => fileRef.current?.click()} data-testid="import-upload-button"><Upload className="h-4 w-4" /> {busy ? "Memeriksa..." : file ? "Ganti Berkas" : "Pilih Berkas Excel"}</Btn>
            <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={pickFile} data-testid="import-file-input" />
            {file && <div className="mt-1 text-xs text-slate-500 break-all" data-testid="import-file-name">{file.name}</div>}
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">3. Proses</div>
            <p className="mt-1 text-sm text-slate-600">Menyimpan baris Baru dan Ubah. Baris Error dilewati. Masuk ke slip draft lewat Fetch Data Terbaru.</p>
            <Btn variant="success" className="mt-2" disabled={busy || !s || s.baru + s.ubah === 0} onClick={commit} data-testid="import-commit-button"><CheckCircle2 className="h-4 w-4" /> Simpan ke RUSA</Btn>
          </div>
        </div>
      </Panel>

      {done && (
        <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900" data-testid="import-done">
          Selesai: <b>{done.saved.baru}</b> karyawan baru, <b>{done.saved.ubah}</b> diubah{done.skipped_errors ? <>, <b>{done.skipped_errors}</b> baris Error dilewati</> : ""}.
          Lihat hasilnya di tab Daftar Karyawan.
        </div>
      )}

      {preview && (
        <div className="mt-4">
          <Panel>
            <div className="px-4 sm:px-5 pt-4 pb-3 border-b border-slate-200">
              <h2 className="text-base font-bold text-slate-900">Pratinjau <span className="num text-slate-500 font-medium">· {s.total} baris</span></h2>
              <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="import-summary">
                <FilterTab label="Semua" count={s.total} on={filter === "all"} onClick={() => setFilter("all")} testId="import-tab-all" />
                {Object.entries(ACTION).map(([k, [label]]) => (
                  <FilterTab key={k} label={label} count={s[k]} on={filter === k} alarm={k === "error" ? "amber" : undefined} disabled={!s[k]}
                    onClick={() => setFilter(filter === k ? "all" : k)} testId={`import-tab-${k}`} />
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]" data-testid="import-table">
                <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                  <tr>{["Baris", "NIK", "Nama", "Hasil", "Keterangan"].map((h) => <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((r) => {
                    const [label, tone, dot] = ACTION[r.action];
                    return (
                      <tr key={r.row} className={r.action === "error" ? "bg-rose-50/40" : ""} data-testid={`import-row-${r.row}`}>
                        <td className="px-3 py-2 num text-slate-500">{r.row}</td>
                        <td className="px-3 py-2 num">{r.nik || "-"}</td>
                        <td className="px-3 py-2 font-medium text-slate-900">{r.name || "-"}</td>
                        <td className="px-3 py-2 whitespace-nowrap"><span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${tone}`}><span className={`h-2 w-2 rounded-full ${dot}`} />{label}</span></td>
                        <td className="px-3 py-2 text-xs text-slate-600">
                          {r.errors.length > 0 && <ul className="list-disc pl-4 text-rose-700">{r.errors.map((m) => <li key={m}>{m}</li>)}</ul>}
                          {r.action === "ubah" && <>Berubah: {r.changes.join(", ")}</>}
                        </td>
                      </tr>
                    );
                  })}
                  {!rows.length && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">Tidak ada baris.</td></tr>}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
