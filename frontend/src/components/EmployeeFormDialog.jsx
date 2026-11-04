import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Btn } from "@/components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Tambah / ubah karyawan yang dikelola di RUSA (user 3 Nov 2026). Aturan isinya sama dengan import Excel (backend
// employees_rusa.validate_row): galat dari server ditampilkan apa adanya.
const EMPTY = {
  nik: "", name: "", gender: "", birth_date: "", email: "", ktp: "", npwp: "", user_id_rumatku: "",
  department: "", position: "", employment_type: "Tetap", join_date: "", exit_date: "", ptkp_status: "TK/0", is_paid: "Paid", is_active: "Aktif",
  basic_salary: "", position_allowance: "", monthly_attendance_allowance: "", overtime_hourly_rate: "", bpjs_kes: "Ya", bpjs_tk: "Ya",
  bank_name: "", bank_code: "", bank_account_number: "", bank_account_name: "",
};
const PTKP = ["TK/0", "TK/1", "TK/2", "TK/3", "K/0", "K/1", "K/2", "K/3"];

// dokumen karyawan -> isian formulir
const fromEmployee = (e) => ({
  ...EMPTY,
  nik: e.nik || "", name: e.name || "", gender: e.gender || "", birth_date: e.birth_date || "", email: e.email || "", ktp: e.ktp || "", npwp: e.npwp || "", user_id_rumatku: e.user_id_rumatku || "",
  department: e.department || "", position: e.position || "", employment_type: e.employment_type || "", join_date: e.join_date || "", exit_date: e.exit_date || "",
  ptkp_status: e.ptkp_status || "TK/0", is_paid: e.payroll_status === "unpaid_leave" ? "Unpaid" : "Paid", is_active: e.is_active === false ? "Nonaktif" : "Aktif",
  basic_salary: e.basic_salary ?? "", position_allowance: e.position_allowance ?? "", monthly_attendance_allowance: e.monthly_attendance_allowance ?? "",
  overtime_hourly_rate: e.overtime_hourly_rate ?? "", bpjs_kes: e.has_bpjs_kes ? "Ya" : "Tidak", bpjs_tk: e.has_bpjs_tk ? "Ya" : "Tidak",
  bank_name: e.bank_name || "", bank_code: e.bank_code || "", bank_account_number: e.bank_account_number || "", bank_account_name: e.bank_account_name || "",
});

const Field = ({ label, required, children, wide }) => (
  <label className={`block text-sm ${wide ? "sm:col-span-2" : ""}`}>
    <span className="mb-1 block text-xs font-semibold text-slate-600">{label}{required && <span className="text-rose-600"> *</span>}</span>
    {children}
  </label>
);
const INPUT = "w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:border-brand-400 focus:ring-2 focus:ring-brand-700/10 outline-none";
const Section = ({ title, children }) => (
  <fieldset className="mt-4">
    <legend className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">{title}</legend>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>
  </fieldset>
);

export default function EmployeeFormDialog({ open, employee, onClose, onSaved }) {
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const edit = !!employee;
  useEffect(() => { if (open) { setF(employee ? fromEmployee(employee) : EMPTY); setError(""); } }, [open, employee]);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const text = (k, props = {}) => <input data-testid={`emp-form-${k}`} className={INPUT} value={f[k]} onChange={set(k)} {...props} />;
  const pick = (k, options) => (
    <select data-testid={`emp-form-${k}`} className={INPUT} value={f[k]} onChange={set(k)}>
      {options.map((o) => <option key={o[0] ?? o} value={o[0] ?? o}>{o[1] ?? o}</option>)}
    </select>
  );

  const save = async () => {
    setBusy(true); setError("");
    try {
      const { data } = edit ? await api.put(`/hr/employees/${employee.id}`, f) : await api.post("/hr/employees", f);
      toast.success(edit ? `Data ${data.name} diperbarui` : `${data.name} ditambahkan`);
      onSaved(); onClose();
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`Hapus ${employee.name} dari RUSA? Hanya bisa bila belum punya slip gaji.`)) return;
    setBusy(true); setError("");
    try { await api.delete(`/hr/employees/${employee.id}`); toast.success(`${employee.name} dihapus`); onSaved(); onClose(); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="employee-form-dialog">
        <DialogHeader>
          <DialogTitle>{edit ? `Ubah Karyawan — ${employee.name}` : "Tambah Karyawan"}</DialogTitle>
          <DialogDescription>Data ini dikelola di RUSA dan tidak ditimpa Fetch dari ROSY. Berlaku di slip draft setelah Fetch Data Terbaru di halaman periode.</DialogDescription>
        </DialogHeader>
        <Section title="Identitas">
          <Field label="NIK" required>{text("nik")}</Field>
          <Field label="Nama" required>{text("name")}</Field>
          <Field label="Jenis Kelamin" required>{pick("gender", [["", "Pilih…"], ["L", "Laki-laki"], ["P", "Perempuan"]])}</Field>
          <Field label="Tgl Lahir">{text("birth_date", { type: "date" })}</Field>
          <Field label="Email">{text("email", { type: "email" })}</Field>
          <Field label="No. KTP">{text("ktp", { inputMode: "numeric" })}</Field>
          <Field label="NPWP" wide>{text("npwp")}</Field>
          <Field label="User ID RUMATKU" wide>{text("user_id_rumatku", { placeholder: "USR-00123 — akun absensi RUMATKU; kosong = hadir penuh" })}</Field>
        </Section>
        <Section title="Kepegawaian">
          <Field label="Departemen">{text("department")}</Field>
          <Field label="Jabatan">{text("position")}</Field>
          <Field label="Status Kepegawaian">{text("employment_type", { placeholder: "Tetap / Kontrak / Training" })}</Field>
          <Field label="Status PTKP" required>{pick("ptkp_status", PTKP)}</Field>
          <Field label="Tgl Masuk">{text("join_date", { type: "date" })}</Field>
          <Field label="Tgl Keluar">{text("exit_date", { type: "date" })}</Field>
          <Field label="Status Gaji">{pick("is_paid", ["Paid", "Unpaid"])}</Field>
          <Field label="Status">{pick("is_active", ["Aktif", "Nonaktif"])}</Field>
        </Section>
        <Section title="Gaji & BPJS">
          <Field label="Gaji Pokok (Rp)" required>{text("basic_salary", { type: "number", min: 0, inputMode: "numeric" })}</Field>
          <Field label="Tunjangan Jabatan (Rp)">{text("position_allowance", { type: "number", min: 0, inputMode: "numeric" })}</Field>
          <Field label="Tunjangan Kehadiran (Rp)">{text("monthly_attendance_allowance", { type: "number", min: 0, inputMode: "numeric" })}</Field>
          <Field label="Tarif Lembur per Jam (Rp)">{text("overtime_hourly_rate", { type: "number", min: 0, inputMode: "numeric" })}</Field>
          <Field label="BPJS Kesehatan">{pick("bpjs_kes", ["Ya", "Tidak"])}</Field>
          <Field label="BPJS Ketenagakerjaan (JKK, JKM, JHT, JP)">{pick("bpjs_tk", ["Ya", "Tidak"])}</Field>
        </Section>
        <Section title="Rekening">
          <Field label="Bank">{text("bank_name", { placeholder: "Bank Syariah Indonesia" })}</Field>
          <Field label="Kode Bank">{text("bank_code", { placeholder: "BSI" })}</Field>
          <Field label="No. Rekening">{text("bank_account_number", { inputMode: "numeric" })}</Field>
          <Field label="Nama di Rekening">{text("bank_account_name")}</Field>
        </Section>
        {error && <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" data-testid="employee-form-error">{error}</div>}
        <div className="mt-5 flex items-center justify-between gap-2">
          <div>{edit && <Btn variant="ghost" className="!text-rose-600 hover:!bg-rose-50" disabled={busy} onClick={remove} data-testid="employee-form-delete"><Trash2 className="h-4 w-4" /> Hapus</Btn>}</div>
          <div className="flex gap-2">
            <Btn variant="outline" disabled={busy} onClick={onClose} data-testid="employee-form-cancel">Batal</Btn>
            <Btn disabled={busy} onClick={save} data-testid="employee-form-save">{busy ? "Menyimpan..." : edit ? "Simpan Perubahan" : "Tambah Karyawan"}</Btn>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
