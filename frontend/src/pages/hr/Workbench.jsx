import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronDown, Save, LockKeyhole, FileText, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, downloadBlob } from "@/lib/api";
import { rp, SLIP_STATUS, PAYROLL_STATUS_LABELS, LEAVE_LABELS, jamMenit } from "@/lib/format";
import { Panel, StatusBadge, Btn } from "@/components/common";
import { useAuth } from "@/context/AuthContext";

const ADJ = ["overtime_hours", "kpi_incentive", "additional_bonus", "other_deductions"];
// Insentif KPI disembunyikan dulu dari review (user 10 Okt 2026); barisnya tetap muncul bila slip sudah berisi nilai,
// supaya Total Pendapatan tetap bisa ditelusuri. Ganti ke true untuk menampilkannya lagi.
const KPI_VISIBLE = false;
// PPT: jenis ketidakhadiran yang ikut memotong gaji pokok & tunjangan jabatan (selain tunjangan kehadiran)
const FULL_CUT = ["alpha", "permission_leave", "approved_unpaid_leave"];

const Row = ({ label, value, hint, tone = "", testId }) => (
  <div className="flex items-start justify-between gap-4 py-2 border-b border-dashed border-slate-200 last:border-0">
    <div>
      <div className="text-sm text-slate-700">{label}</div>
      {hint && <div className="text-[11px] text-slate-400">{hint}</div>}
    </div>
    <div data-testid={testId} className={`num text-sm font-medium whitespace-nowrap ${tone}`}>{value}</div>
  </div>
);

// Saat slip/periode terkunci, isian tampil seperti baris biasa: tanpa label EDITABLE dan tanpa warna kuning
const Edit = ({ label, hint, value, onChange, disabled, testId, suffix }) => disabled ? (
  <Row label={label} hint={hint} value={rp(value)} testId={testId} />
) : (
  <div className="flex items-center justify-between gap-4 py-2 border-b border-dashed border-slate-200">
    <div>
      <div className="text-sm text-slate-800 font-medium flex items-center gap-1.5">{label}<span className="text-[9px] font-bold tracking-wider text-amber-700 bg-amber-100 border border-amber-300 px-1 rounded">EDITABLE</span></div>
      {hint && <div className="text-[11px] text-slate-400">{hint}</div>}
    </div>
    <div className="flex items-center gap-1.5">
      <input data-testid={testId} type="number" min="0" disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)} className="amber-input w-36 text-sm disabled:opacity-60" />
      {suffix && <span className="text-xs text-slate-500 w-6">{suffix}</span>}
    </div>
  </div>
);

export default function Workbench() {
  const { pid, eid } = useParams();
  const [d, setD] = useState(null);
  const [adj, setAdj] = useState(null);
  const [notes, setNotes] = useState("");
  const [calc, setCalc] = useState(null);
  const [busy, setBusy] = useState(false);
  // Log presensi dilipat secara bawaan supaya halaman review tidak terlalu panjang (permintaan user 10 Okt 2026)
  const [logOpen, setLogOpen] = useState(false);
  const first = useRef(true);
  const { user } = useAuth();
  const isManager = user?.role === "manager_hrd";

  const load = () => api.get(`/hr/periods/${pid}/employees/${eid}`).then((r) => {
    setD(r.data);
    setCalc(r.data.payslip);
    setAdj(Object.fromEntries(ADJ.map((k) => [k, r.data.payslip[k] ?? 0])));
    setNotes(r.data.payslip.adjustment_notes || "");
    first.current = true;
  });
  useEffect(() => { load(); }, [pid, eid]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!adj) return;
    if (first.current) { first.current = false; return; }
    const t = setTimeout(() => {
      api.post(`/hr/periods/${pid}/employees/${eid}/preview`, numeric(adj)).then((r) => setCalc(r.data)).catch((e) => toast.error(errMsg(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [adj, pid, eid]);

  const numeric = (a) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, Number(v) || 0]));
  const set = (k) => (v) => setAdj({ ...adj, [k]: v });

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/hr/periods/${pid}/employees/${eid}`, { ...numeric(adj), adjustment_notes: notes });
      toast.success("Draft tersimpan");
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const approve = async () => {
    setBusy(true);
    try {
      await api.put(`/hr/periods/${pid}/employees/${eid}`, { ...numeric(adj), adjustment_notes: notes });
      await api.post(`/hr/periods/${pid}/employees/${eid}/approve`);
      toast.success("Slip dikunci & di-approve, PDF terenkripsi dibuat");
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const pdf = () => downloadBlob(`/hr/periods/${pid}/employees/${eid}/pdf`, "preview.pdf", true).catch((e) => toast.error(errMsg(e)));

  if (!d || !calc) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { employee: emp, period, payslip, attendance } = d;
  const locked = payslip.status === "approved" || (!isManager && !(["draft", "revision"].includes(period.status)));
  const dc = calc.discipline || payslip.discipline;
  const bp = calc.bpjs || payslip.bpjs;
  const wd = calc.work_days || 25;
  // Poin Absensi = hanya hari yang juga memotong gaji pokok (alfa/izin); sakit, cuti dll masuk Poin Presensi
  const absence = Object.entries(dc.absence_by_type || {});
  const presenceLeave = Object.entries(dc.presence_by_type || {});
  // Susunan sama dengan slip PDF (pdf_service.payslip_lines): tunjangan tampil penuh di Pendapatan, semua potongan
  // karena kehadiran di Potongan. Kedua total ikut memuatnya, jadi Total Diterima & dasar PPh 21 tidak berubah.
  const split = calc.presence_penalty_amount !== undefined; // slip lama hanya punya tunjangan kehadiran bersih
  const presensi = calc.presence_penalty_amount || 0;
  const absensi = (calc.absence_penalty_amount || 0) + (calc.absent_deduction_amount || 0) + (calc.position_deduction_amount || 0);
  const totalPendapatan = calc.gross_earnings + presensi + absensi;
  const totalPotongan = calc.total_deductions + presensi + absensi;
  // divisi Pelayanan: tunjangan jabatan disebut "Bonus Threshold" (aturan di backend labels.py, user 12 Okt 2026)
  const jabatan = calc.position_allowance_label || payslip.position_allowance_label || "Tunjangan Jabatan";
  const absensiHint = [
    calc.absence_penalty_amount > 0 && `Tj. Kehadiran ${rp(calc.absence_penalty_amount)}`,
    calc.absent_deduction_amount > 0 && `Gaji Pokok ${rp(calc.absent_deduction_amount)}`,
    calc.position_deduction_amount > 0 && `${jabatan === "Tunjangan Jabatan" ? "Tj. Jabatan" : jabatan} ${rp(calc.position_deduction_amount)}`,
  ].filter(Boolean).join(" · ");

  return (
    <div className="pb-36" data-testid="workbench-page">
      <Link to={`/hr-manager/payroll/${pid}`} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> {period.period_name}</Link>
      <div className="bg-white border border-slate-200 rounded-lg p-5 mb-6 flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500 num">{emp.nik} · {emp.department}</div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="workbench-employee-name">{emp.name}</h1>
        </div>
        <Info k="Status Payroll" v={PAYROLL_STATUS_LABELS[emp.payroll_status]} />
        <Info k="Status PTKP" v={`${calc.ptkp_status} · TER ${calc.ter_category}`} testId="workbench-ptkp" />
        <Info k="Rekening" v={`${emp.bank_account_number || "-"} (${(emp.bank_code || emp.bank_name || "-").toUpperCase()})`} />
        <div className="ml-auto"><StatusBadge map={SLIP_STATUS} status={payslip.status} testId="workbench-slip-status" /></div>
      </div>
      {emp.gender === "P" && emp.marital_status === "K" && !emp.has_husband_certificate && (
        <div className="mb-4 flex items-center gap-2 text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-md px-4 py-2.5" data-testid="ptkp-female-notice"><AlertTriangle className="h-4 w-4" /> Karyawati menikah tanpa Surat Keterangan Suami Tidak Berpenghasilan → PTKP dikunci TK/0 (TER A).</div>
      )}
      {calc.payroll_status === "unpaid_leave" && (
        <div className="mb-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-2.5" data-testid="unpaid-leave-notice">Cuti di luar tanggungan: upah & tunjangan Rp 0. Iuran BPJS ditalangi perusahaan (kasbon) sebesar <b className="num">{rp(calc.bpjs_company_advance)}</b>.</div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Panel title="Pendapatan" right={<span className="num text-sm font-bold">{rp(totalPendapatan)}</span>}>
          <div className="px-5 py-2">
            <Row label="Gaji Pokok" hint={calc.wage_multiplier !== 1 ? `Pengali upah ${calc.wage_multiplier * 100}% dari ${rp(calc.basic_salary_contract)}` : null} value={rp(calc.basic_salary)} testId="earn-basic" />
            <Row label={jabatan} value={rp(calc.position_allowance)} testId="earn-position" />
            <Row label={split ? "Tunjangan Kehadiran" : "Tunjangan Kehadiran (bersih)"} value={rp(split ? calc.attendance_allowance_base : calc.attendance_allowance)} testId="earn-attendance" />
            {(emp.overtime_access || calc.overtime_hours > 0 || calc.overtime_pay > 0) && <Row label={`Lembur (${jamMenit(calc.overtime_hours)} dari RUMATKU)`} hint={`${rp(emp.overtime_hourly_rate)}/jam`} value={rp(calc.overtime_pay)} testId="earn-overtime" />}
            <Row label="Transport Homecare" hint="Dari ROSY (Tambahan Bulanan: Transport Rumat Kita)" value={rp(calc.transport_homecare || 0)} testId="earn-transport" />
            {(KPI_VISIBLE || Number(adj.kpi_incentive) !== 0) && <Edit label="Insentif KPI" value={adj.kpi_incentive} onChange={set("kpi_incentive")} disabled={locked} testId="input-kpi-incentive" />}
            <Row label="Bonus" hint="Dari ROSY (Tambahan Bulanan: Bonus)" value={rp(calc.additional_bonus || 0)} testId="earn-bonus" />
            {calc.thr > 0 && <Row label="THR" hint="Dari ROSY (Tambahan Bulanan: THR)" value={rp(calc.thr)} testId="earn-thr" />}
            <Row label="Tunjangan BPJS Kesehatan (4%)" hint={`Basis ${rp(bp.kes_base)} (max gaji pokok, UMK Bekasi)`} value={rp(calc.tunjangan_bpjs_kes)} testId="earn-bpjs-kes" />
            <Row label="Tunjangan BPJS TK" hint={`JKK ${rp(bp.jkk)} · JKM ${rp(bp.jkm)} · JHT 3,7% ${rp(bp.jht_company)} · JP 2% ${rp(bp.jp_company)}`} value={rp(calc.tunjangan_bpjs_tk)} testId="earn-bpjs-tk" />
          </div>
          <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-600 flex items-center justify-between gap-4"><span title="Pendapatan − Potongan Presensi & Absensi − JHT & JP perusahaan">Bruto Objek Pajak (dasar TER)</span><b className="num text-slate-900 whitespace-nowrap" data-testid="taxable-gross">{rp(calc.taxable_gross)}</b></div>
        </Panel>
        <div className="space-y-6">
          <Panel title="Potongan" right={<span className="num text-sm font-bold text-rose-600">{rp(totalPotongan)}</span>}>
            <div className="px-5 py-2">
              {split && <Row label="Potongan Presensi" hint={`${calc.late_penalty_points} poin presensi × 1/${wd} Tunjangan Kehadiran`} value={rp(presensi)} tone={presensi > 0 ? "text-rose-600" : ""} testId="ded-presensi" />}
              <Row label="Potongan Absensi" hint={`${calc.absence_points ?? calc.absent_days ?? 0} hari alfa/izin${absensiHint ? ` — ${absensiHint}` : ""}`} value={rp(absensi)} tone={absensi > 0 ? "text-rose-600" : ""} testId="ded-absensi" />
              {calc.target_deduction > 0 && <Row label="Potongan Tidak Mencapai Target" hint="Dari ROSY (Tambahan Bulanan: Potongan Tidak Mencapai Target)" value={rp(calc.target_deduction)} tone="text-rose-600" testId="ded-target" />}
              <Row label="Iuran BPJS Kesehatan (5%)" hint={`Perusahaan ${rp(bp.kes_company)} + Karyawan ${rp(bp.kes_employee)}`} value={rp(calc.iuran_bpjs_kes_total)} testId="ded-bpjs-kes" />
              <Row label="Iuran BPJS Ketenagakerjaan" hint={`JKK+JKM ${rp(bp.jkk + bp.jkm)} · JHT ${rp(bp.jht_company + bp.jht_employee)} · JP ${rp(bp.jp_company + bp.jp_employee)}`} value={rp(calc.iuran_bpjs_tk_total)} testId="ded-bpjs-tk" />
              {calc.tax_reconciliation ? (
                <Row label="PPh 21 Masa Desember (Pasal 17)" hint={calc.pph21_amount < 0 ? "Lebih bayar — dikembalikan ke karyawan" : "Terutang setahun − dipotong Jan–Nov"} value={rp(calc.pph21_amount)} tone={calc.pph21_amount < 0 ? "text-emerald-600" : ""} testId="ded-pph21" />
              ) : (
                <Row label={`PPh 21 TER ${calc.ter_category}`} hint={`${calc.ter_rate}% × ${rp(calc.taxable_gross)}`} value={rp(calc.pph21_amount)} testId="ded-pph21" />
              )}
              {calc.loan_installment > 0 && <Row label="Cicilan / Pinjaman" hint="Dari ROSY (Tambahan Bulanan: Cicilan / Pinjaman)" value={rp(calc.loan_installment)} tone="text-rose-600" testId="ded-loan" />}
              <Edit label="Kasbon / Potongan Lain" value={adj.other_deductions} onChange={set("other_deductions")} disabled={locked} testId="input-other-deductions" />
            </div>
          </Panel>
          {calc.tax_reconciliation && <Recon r={calc.tax_reconciliation} ptkp={calc.ptkp_status} />}
          <textarea data-testid="adjustment-notes-input" disabled={locked} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Catatan penyesuaian manajerial..." className="w-full border border-slate-300 rounded-md p-3 text-sm min-h-[70px]" />
        </div>
      </div>
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Panel title="Poin Presensi" right={<span className="num text-sm font-bold text-rose-600" data-testid="presence-total">{calc.late_penalty_points} poin</span>}>
          <div className="grid grid-cols-4 divide-x divide-slate-200 text-center" data-testid="waterfall-summary">
            {[["Rule 1", dc.rule1_points, "Lupa tap"], ["Rule 2", dc.rule2_points, "≥ 60 m"], ["Rule 3", dc.rule3_points, `${dc.rule3_events} × 15–59 m`], ["Rule 4", dc.rule4_points, `${dc.rule4_minutes} m akumulasi`]].map(([k, v, h]) => (
              <div key={k} className="py-4"><div className="text-[11px] uppercase tracking-wider text-slate-500">{k}</div><div className="num text-2xl font-bold text-rose-600" data-testid={`waterfall-${k.replace(" ", "").toLowerCase()}`}>{v}</div><div className="text-[11px] text-slate-400">{h}</div></div>
            ))}
          </div>
          <div className="px-5 py-3 border-t border-slate-200 text-xs text-slate-600">Keterlambatan (Rule 1–4) <b className="num" data-testid="waterfall-total">{dc.total_points} poin</b>{dc.rule3_carried_minutes?.length ? ` · sisa Rule 3 diteruskan: ${dc.rule3_carried_minutes.join(", ")} m` : ""} · menit hangus {dc.rule4_forfeited_minutes} m</div>
          {presenceLeave.length > 0 && (
            <div className="px-5 py-2 border-t border-slate-200" data-testid="presence-leave-breakdown">
              {presenceLeave.map(([lt, n]) => (
                <Row key={lt} label={LEAVE_LABELS[lt] || lt} hint="1 poin per hari · memotong Tj. Kehadiran saja" value={`${n} poin`} />
              ))}
            </div>
          )}
        </Panel>
        <div className="space-y-6">
          <Panel title="Poin Absensi" right={<span className="num text-sm font-bold text-rose-600" data-testid="absence-total">{calc.absence_points ?? dc.basic_cut_days ?? 0} hari</span>}>
            <div className="px-5 py-2" data-testid="absence-breakdown">
              {absence.map(([lt, n]) => (
                <Row key={lt} label={LEAVE_LABELS[lt] || lt} hint={FULL_CUT.includes(lt) ? "Memotong gaji pokok, Tj. Jabatan & Tj. Kehadiran" : "Memotong Tj. Kehadiran"} value={`${n} hari`} />
              ))}
              {!absence.length && <div className="py-2 text-sm text-slate-500">Tidak ada alfa/mangkir atau izin.</div>}
            </div>
          </Panel>
          <section className="bg-white border border-slate-200 rounded-lg shadow-sm" data-testid="attendance-log">
            <button type="button" onClick={() => setLogOpen(!logOpen)} aria-expanded={logOpen} data-testid="attendance-log-toggle" className={`w-full flex items-center justify-between px-5 py-3 text-left hover:bg-slate-50 ${logOpen ? "rounded-t-lg border-b border-slate-200" : "rounded-lg"}`}>
              <span className="text-sm font-semibold text-slate-800 uppercase tracking-wider">Log Presensi ({attendance.length})</span>
              <span className="flex items-center gap-1 text-xs text-slate-500">{logOpen ? "Sembunyikan" : "Tampilkan"}<ChevronDown className={`h-4 w-4 transition-transform ${logOpen ? "rotate-180" : ""}`} /></span>
            </button>
            {logOpen && (
              <div className="max-h-56 overflow-y-auto text-xs">
                {attendance.map((a) => (
                  <div key={a.id} className="flex justify-between px-5 py-1.5 border-b border-slate-100 num">
                    <span>{a.work_date}</span><span className="text-slate-500">{LEAVE_LABELS[a.leave_type]}</span>
                    <span className={a.minutes_late ? "text-rose-600" : ""}>telat {a.minutes_late || 0}m</span>
                    <span className={a.minutes_early_leave ? "text-rose-600" : ""}>cepat {a.minutes_early_leave || 0}m</span>
                  </div>
                ))}
                {!attendance.length && <div className="px-5 py-4 text-slate-500">Tidak ada log (dianggap hadir penuh).</div>}
              </div>
            )}
          </section>
        </div>
      </div>
      <div className="fixed bottom-0 inset-x-0 z-50 bg-white/95 backdrop-blur-md border-t-2 border-emerald-500 shadow-[0_-4px_20px_rgba(0,0,0,0.08)]">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-3 flex flex-col md:flex-row md:items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">Total Diterima · Pendapatan {rp(totalPendapatan)} − Potongan {rp(totalPotongan)}</div>
            <div className="num text-2xl font-black text-emerald-600" data-testid="sticky-thp">{rp(calc.take_home_pay)}</div>
            <div className="text-xs italic text-slate-500 truncate" data-testid="sticky-terbilang">{calc.terbilang}</div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Btn variant="outline" onClick={pdf} data-testid="preview-pdf-button"><FileText className="h-4 w-4" /> Preview PDF Slip</Btn>
            <Btn variant="primary" onClick={save} disabled={busy || locked} data-testid="save-draft-button"><Save className="h-4 w-4" /> Simpan Draft</Btn>
            {isManager && <Btn variant="success" onClick={approve} disabled={busy || payslip.status === "approved"} title={payslip.status === "approved" ? "Slip sudah dikunci & di-approve" : ""} data-testid="approve-lock-button"><LockKeyhole className="h-4 w-4" /> Lock & Approve</Btn>}
          </div>
        </div>
      </div>
    </div>
  );
}

const Info = ({ k, v, testId }) => (
  <div><div className="text-[11px] uppercase tracking-wider text-slate-500">{k}</div><div className="text-sm font-semibold" data-testid={testId}>{v}</div></div>
);

const Recon = ({ r, ptkp }) => (
  <Panel title={`Rekonsiliasi Pasal 17 · ${r.tax_year}`} right={!r.has_initial_balance && <span className="text-[11px] text-amber-700" data-testid="recon-no-ytd">Tanpa saldo awal YTD</span>}>
    <div className="px-5 py-2" data-testid="tax-reconciliation-panel">
      <Row label="Saldo awal YTD (impor)" value={rp(r.initial_gross)} />
      <Row label={`Bruto sistem (${r.system_months} bulan)`} value={rp(r.system_gross)} />
      <Row label="Bruto Desember" value={rp(r.december_gross)} />
      <Row label="Bruto setahun" value={rp(r.gross_year)} tone="font-semibold" testId="recon-gross-year" />
      <Row label="Biaya jabatan (5%, maks 6 jt)" value={`- ${rp(r.biaya_jabatan)}`} />
      <Row label="JHT + JP pekerja setahun" value={`- ${rp(r.jht_jp_year)}`} />
      <Row label="Neto setahun" value={rp(r.neto_year)} />
      <Row label={`PTKP ${ptkp}`} value={`- ${rp(r.ptkp_amount)}`} />
      <Row label="PKP (dibulatkan ribuan)" value={rp(r.pkp)} testId="recon-pkp" />
      <Row label="PPh 21 terutang setahun" value={rp(r.annual_tax)} testId="recon-annual-tax" />
      <Row label="Sudah dipotong Jan–Nov" value={`- ${rp(r.pph21_paid_jan_nov)}`} />
      <Row label="PPh 21 Desember" value={rp(r.pph21_december)} tone="font-bold" testId="recon-december" />
    </div>
  </Panel>
);
