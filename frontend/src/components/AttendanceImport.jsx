import { useRef, useState } from "react";
import { Upload, FileDown } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg } from "@/lib/api";
import { Panel, Btn } from "@/components/common";

export const AttendanceImport = ({ onDone }) => {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post("/hr/attendance/import", fd);
      setRes(data);
      toast.success(`Impor selesai: ${data.created} baru, ${data.updated} diperbarui`);
      onDone();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); e.target.value = ""; }
  };
  const template = () => saveFile("get", "/hr/attendance/import-template", "template_absensi_rumatku.csv").catch(async (e) => toast.error(await blobErrMsg(e)));

  return (
    <Panel title="Impor Rekap Rumatku">
      <div className="p-5 space-y-3" data-testid="attendance-import-panel">
        <p className="text-xs text-slate-500">CSV / Excel berisi nik, tanggal, jam_masuk, jam_pulang, foto_masuk, foto_pulang, lokasi_masuk, lokasi_pulang. Shift dideteksi otomatis (rotasi › jam terdekat).</p>
        <div className="flex gap-2">
          <Btn variant="outline" onClick={template} data-testid="att-import-template-button"><FileDown className="h-4 w-4" /> Template</Btn>
          <Btn onClick={() => ref.current?.click()} disabled={busy} data-testid="att-import-button" className="flex-1 justify-center"><Upload className="h-4 w-4" /> {busy ? "Mengimpor..." : "Unggah File"}</Btn>
          <input ref={ref} type="file" accept=".csv,.xlsx" className="hidden" onChange={upload} data-testid="att-import-file-input" />
        </div>
        {res && (
          <div className="text-xs space-y-1.5" data-testid="att-import-result">
            <div className="font-semibold text-slate-700">{res.created} baru · {res.updated} diperbarui · {res.skipped.length} dilewati · {res.errors.length} error</div>
            <div className="flex flex-wrap gap-1.5">{Object.entries(res.shift_summary).map(([k, v]) => <span key={k} className="num bg-slate-100 rounded px-1.5 py-0.5">{k}: {v}</span>)}</div>
            {[...res.skipped, ...res.errors].map((m) => <div key={m} className="text-rose-600">{m}</div>)}
          </div>
        )}
      </div>
    </Panel>
  );
};
