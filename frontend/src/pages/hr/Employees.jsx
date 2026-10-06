import { useEffect, useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, PAYROLL_STATUS_LABELS } from "@/lib/format";
import { PageTitle, Panel, Btn } from "@/components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const EMPTY = {
  nik: "", name: "", email: "", department: "", birth_date: "", gender: "L", marital_status: "TK", dependents_count: 0,
  has_husband_certificate: false, payroll_status: "active", prolonged_illness_month_count: 0, basic_salary: 0,
  position_allowance: 0, monthly_attendance_allowance: 0, overtime_hourly_rate: 0, has_bpjs_kes: true, has_bpjs_tk: true,
  jkk_rate: 0.0024, bank_name: "BSI", bank_account_number: "", password: "",
};
const NUM = ["dependents_count", "prolonged_illness_month_count", "basic_salary", "position_allowance", "monthly_attendance_allowance", "overtime_hourly_rate", "jkk_rate"];

const In = ({ label, k, f, setF, type = "text", ...p }) => (
  <label className="block space-y-1">
    <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
    <input data-testid={`emp-${k}-input`} type={type} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm" {...p} />
  </label>
);
const Sel = ({ label, k, f, setF, opts }) => (
  <label className="block space-y-1">
    <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
    <select data-testid={`emp-${k}-select`} value={String(f[k])} onChange={(e) => setF({ ...f, [k]: ["true", "false"].includes(e.target.value) ? e.target.value === "true" : e.target.value })} className="w-full border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white">
      {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  </label>
);

export default function Employees() {
  const [list, setList] = useState([]);
  const [f, setF] = useState(null);
  const load = () => api.get("/hr/employees").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault();
    const body = { ...f };
    NUM.forEach((k) => (body[k] = Number(body[k]) || 0));
    if (!body.password) delete body.password;
    try {
      if (f.id) await api.put(`/hr/employees/${f.id}`, body); else await api.post("/hr/employees", body);
      toast.success("Profil gaji tersimpan");
      setF(null);
      load();
    } catch (err) { toast.error(errMsg(err)); }
  };

  return (
    <div>
      <PageTitle title="Karyawan & Profil Gaji" subtitle="employee_salary_profiles">
        <Btn data-testid="add-employee-button" onClick={() => setF({ ...EMPTY })}><Plus className="h-4 w-4" /> Tambah Karyawan</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="employees-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>{["NIK", "Nama", "Dept", "L/P", "Status Nikah", "Status Payroll", "Gaji Pokok", "Tunj. Jabatan", "Tunj. Hadir", "Rekening", ""].map((h) => <th key={h} className="text-left px-4 py-3">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50" data-testid={`employee-row-${e.nik}`}>
                  <td className="px-4 py-3 num">{e.nik}</td>
                  <td className="px-4 py-3 font-semibold">{e.name}<div className="text-xs font-normal text-slate-500">{e.email}</div></td>
                  <td className="px-4 py-3 text-slate-600">{e.department}</td>
                  <td className="px-4 py-3">{e.gender}</td>
                  <td className="px-4 py-3 num">{e.marital_status}/{e.dependents_count}{e.has_husband_certificate ? " ✓SK" : ""}</td>
                  <td className="px-4 py-3 text-xs">{PAYROLL_STATUS_LABELS[e.payroll_status]}</td>
                  <td className="px-4 py-3 num">{rp(e.basic_salary)}</td>
                  <td className="px-4 py-3 num">{rp(e.position_allowance)}</td>
                  <td className="px-4 py-3 num">{rp(e.monthly_attendance_allowance)}</td>
                  <td className="px-4 py-3 num text-xs">{e.bank_name} {e.bank_account_number}</td>
                  <td className="px-4 py-3"><button data-testid={`edit-employee-${e.nik}`} onClick={() => setF({ ...EMPTY, ...e, password: "" })} className="p-1.5 rounded hover:bg-slate-100"><Pencil className="h-4 w-4" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Dialog open={!!f} onOpenChange={(o) => !o && setF(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="employee-dialog">
          <DialogHeader><DialogTitle>{f?.id ? "Edit" : "Tambah"} Profil Gaji</DialogTitle></DialogHeader>
          {f && (
            <form onSubmit={save} className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <In label="NIK" k="nik" f={f} setF={setF} required />
                <In label="Nama" k="name" f={f} setF={setF} required />
                <In label="Email" k="email" type="email" f={f} setF={setF} required />
                <In label="Departemen" k="department" f={f} setF={setF} />
                <In label="Tanggal Lahir (sandi PDF)" k="birth_date" type="date" f={f} setF={setF} required />
                <In label={f.id ? "Password baru (opsional)" : "Password login"} k="password" type="password" f={f} setF={setF} placeholder="Password123!" />
                <Sel label="Gender" k="gender" f={f} setF={setF} opts={[["L", "Laki-laki"], ["P", "Perempuan"]]} />
                <Sel label="Status Nikah" k="marital_status" f={f} setF={setF} opts={[["TK", "TK (Belum Kawin)"], ["K", "K (Kawin)"]]} />
                <In label="Jumlah Tanggungan" k="dependents_count" type="number" min="0" max="3" f={f} setF={setF} />
                <Sel label="SK Suami Tdk Berpenghasilan" k="has_husband_certificate" f={f} setF={setF} opts={[["false", "Tidak ada"], ["true", "Ada"]]} />
                <Sel label="Status Payroll" k="payroll_status" f={f} setF={setF} opts={Object.entries(PAYROLL_STATUS_LABELS)} />
                <In label="Bulan ke- (sakit/STMB)" k="prolonged_illness_month_count" type="number" min="0" f={f} setF={setF} />
                <In label="Gaji Pokok" k="basic_salary" type="number" f={f} setF={setF} required />
                <In label="Tunjangan Jabatan" k="position_allowance" type="number" f={f} setF={setF} />
                <In label="Tunjangan Kehadiran" k="monthly_attendance_allowance" type="number" f={f} setF={setF} />
                <In label="Tarif Lembur / Jam" k="overtime_hourly_rate" type="number" f={f} setF={setF} />
                <In label="Tarif JKK" k="jkk_rate" type="number" step="0.0001" f={f} setF={setF} />
                <Sel label="BPJS Kesehatan" k="has_bpjs_kes" f={f} setF={setF} opts={[["true", "Ya"], ["false", "Tidak"]]} />
                <Sel label="BPJS TK" k="has_bpjs_tk" f={f} setF={setF} opts={[["true", "Ya"], ["false", "Tidak"]]} />
                <In label="Bank" k="bank_name" f={f} setF={setF} />
                <In label="No. Rekening" k="bank_account_number" f={f} setF={setF} />
              </div>
              <Btn data-testid="employee-submit-button" className="w-full justify-center">Simpan Profil</Btn>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
