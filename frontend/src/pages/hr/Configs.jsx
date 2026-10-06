import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PageTitle, Panel, Btn } from "@/components/common";

export default function Configs() {
  const [list, setList] = useState([]);
  const [vals, setVals] = useState({});
  const load = () => api.get("/hr/configs").then((r) => {
    setList(r.data);
    setVals(Object.fromEntries(r.data.map((c) => [c.config_key, c.config_value])));
  });
  useEffect(() => { load(); }, []);

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
      <Panel>
        <div className="divide-y divide-slate-100">
          {list.map((c) => (
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
