import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Play, LockKeyhole, ChevronLeft } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { rp, PERIOD_STATUS, SLIP_STATUS, PAYROLL_STATUS_LABELS } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, Btn } from "@/components/common";

export default function PeriodDetail() {
  const { pid } = useParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get(`/hr/periods/${pid}`).then((r) => setD(r.data)), [pid]);
  useEffect(() => { load(); }, [load]);

  const act = async (path, msg) => {
    setBusy(true);
    try {
      await api.post(`/hr/periods/${pid}/${path}`);
      toast.success(msg);
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, payslips } = d;
  const locked = ["approved", "closed"].includes(period.status);
  const sum = (k) => payslips.reduce((a, s) => a + (s[k] || 0), 0);

  return (
    <div data-testid="period-detail-page">
      <Link to="/hr-manager/payroll" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua periode</Link>
      <PageTitle title={period.period_name} subtitle={`${period.start_date} → ${period.end_date} · Transfer ${period.payment_date || "-"}`}>
        <StatusBadge map={PERIOD_STATUS} status={period.status} testId="period-status-badge" />
        <Btn variant="outline" data-testid="process-payroll-button" disabled={busy || locked} onClick={() => act("process", "Batch payroll selesai dihitung")}><Play className="h-4 w-4" /> Proses Payroll</Btn>
        <Btn variant="success" data-testid="approve-all-button" disabled={busy || locked || !payslips.length} onClick={() => act("approve-all", "Semua slip di-approve & dikunci")}><LockKeyhole className="h-4 w-4" /> Approve & Lock Semua</Btn>
      </PageTitle>
      <Panel>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="payslips-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                {["NIK", "Nama", "Status", "PTKP / TER", "Poin Denda", "Bruto Komersial", "Bruto Pajak", "PPh 21", "Potongan", "THP", "Slip", ""].map((h, i) => (
                  <th key={h + i} className={`px-4 py-3 ${i > 3 && i < 10 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {payslips.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50" data-testid={`payslip-row-${s.employee.nik}`}>
                  <td className="px-4 py-3 num text-slate-600">{s.employee.nik}</td>
                  <td className="px-4 py-3 font-semibold">{s.employee.name}{s.is_manually_adjusted && <span className="ml-2 text-[10px] text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">EDIT</span>}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{PAYROLL_STATUS_LABELS[s.payroll_status]}</td>
                  <td className="px-4 py-3 num text-xs">{s.ptkp_status} · {s.ter_category} {s.ter_rate}%</td>
                  <td className={`px-4 py-3 num text-right ${s.late_penalty_points ? "text-rose-600 font-semibold" : ""}`}>{s.late_penalty_points}</td>
                  <td className="px-4 py-3 num text-right">{rp(s.gross_earnings)}</td>
                  <td className="px-4 py-3 num text-right text-slate-600">{rp(s.taxable_gross)}</td>
                  <td className="px-4 py-3 num text-right">{rp(s.pph21_amount)}</td>
                  <td className="px-4 py-3 num text-right text-rose-600">{rp(s.total_deductions)}</td>
                  <td className="px-4 py-3 num text-right font-bold text-emerald-600" data-testid={`thp-${s.employee.nik}`}>{rp(s.take_home_pay)}</td>
                  <td className="px-4 py-3"><StatusBadge map={SLIP_STATUS} status={s.status} /></td>
                  <td className="px-4 py-3 text-right"><Link to={`/hr-manager/payroll/${pid}/employee/${s.employee_id}`} data-testid={`review-${s.employee.nik}`} className="text-blue-900 font-semibold hover:underline whitespace-nowrap">Review</Link></td>
                </tr>
              ))}
              {!payslips.length && <tr><td colSpan={12} className="px-4 py-8 text-center text-slate-500">Belum ada slip. Klik "Proses Payroll".</td></tr>}
            </tbody>
            {!!payslips.length && (
              <tfoot className="bg-slate-50 font-semibold">
                <tr>
                  <td colSpan={5} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Total {payslips.length} karyawan</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("gross_earnings"))}</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("taxable_gross"))}</td>
                  <td className="px-4 py-3 num text-right">{rp(sum("pph21_amount"))}</td>
                  <td className="px-4 py-3 num text-right text-rose-600">{rp(sum("total_deductions"))}</td>
                  <td className="px-4 py-3 num text-right text-emerald-600" data-testid="total-thp">{rp(sum("take_home_pay"))}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Panel>
    </div>
  );
}
