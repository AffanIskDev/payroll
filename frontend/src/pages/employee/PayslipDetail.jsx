import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, Download, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, downloadBlob } from "@/lib/api";
import { rp } from "@/lib/format";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const Line = ({ k, v, neg, testId }) => (
  <div className="flex justify-between py-1.5 text-sm">
    <span className="text-slate-600">{k}</span>
    <span data-testid={testId} className={`num font-medium ${neg ? "text-rose-600" : ""}`}>{neg && v ? "- " : ""}{rp(v)}</span>
  </div>
);

export default function PayslipDetail() {
  const { sid } = useParams();
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/v1/employee/payslips/${sid}`).then((r) => setS(r.data)).catch((e) => toast.error(errMsg(e))); }, [sid]);

  const download = async () => {
    setBusy(true);
    try {
      await downloadBlob(`/v1/employee/payslips/${sid}/download`, `Slip-Gaji-${s.period.period_name.replace(/\s/g, "-")}.pdf`);
      toast.success("Slip diunduh. Buka dengan sandi DDMMYY.");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!s) return <div className="max-w-md mx-auto p-6 text-sm text-slate-500">Memuat...</div>;
  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-50 pb-40 sm:border-x border-slate-200" data-testid="payslip-detail">
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <Link to="/me" data-testid="back-to-home" className="p-2 rounded-full bg-white border border-slate-200"><ChevronLeft className="h-4 w-4" /></Link>
        <div className="font-semibold">Slip Gaji {s.period.period_name}</div>
      </div>
      <div className="px-4">
        <div className="rounded-2xl text-white p-6 shadow-lg relative overflow-hidden" style={{ background: "linear-gradient(135deg,#0F766E 0%,#0D9488 55%,#14B8A6 100%)" }}>
          <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
          <div className="text-xs text-teal-50 uppercase tracking-wider">Take Home Pay</div>
          <div className="num text-3xl font-extrabold mt-1" data-testid="detail-thp">{rp(s.take_home_pay)}</div>
          <div className="text-[11px] italic text-teal-50 mt-2">{s.terbilang}</div>
          <div className="mt-4 text-xs text-teal-50">{s.employee.bank_name} · {s.employee.bank_account_number || "-"}</div>
        </div>
      </div>
      <Accordion type="multiple" defaultValue={["earn"]} className="px-4 mt-5 space-y-3">
        <AccordionItem value="earn" className="bg-white rounded-xl border border-slate-200 px-4">
          <AccordionTrigger data-testid="accordion-earnings" className="text-sm font-semibold">Penerimaan <span className="num ml-auto mr-2 text-teal-700">{rp(s.gross_earnings)}</span></AccordionTrigger>
          <AccordionContent>
            <Line k="Gaji Pokok" v={s.basic_salary} />
            {s.absent_deduction_amount > 0 && <Line k="Potongan Mangkir" v={s.absent_deduction_amount} neg />}
            <Line k="Tunjangan Jabatan" v={s.position_allowance} />
            <Line k="Tunjangan Kehadiran (bersih)" v={s.attendance_allowance} testId="detail-attendance-net" />
            <Line k={`Lembur (${s.overtime_hours} jam)`} v={s.overtime_pay} />
            <Line k="Insentif KPI" v={s.kpi_incentive} />
            <Line k="Bonus Tambahan" v={s.additional_bonus} />
            <Line k="Tunjangan BPJS Kesehatan" v={s.tunjangan_bpjs_kes} />
            <Line k="Tunjangan BPJS TK" v={s.tunjangan_bpjs_tk} />
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="ded" className="bg-white rounded-xl border border-slate-200 px-4">
          <AccordionTrigger data-testid="accordion-deductions" className="text-sm font-semibold">Potongan <span className="num ml-auto mr-2 text-rose-600">{rp(s.total_deductions)}</span></AccordionTrigger>
          <AccordionContent>
            <Line k="Iuran BPJS Kesehatan" v={s.iuran_bpjs_kes_total} neg />
            <Line k="Iuran BPJS Ketenagakerjaan" v={s.iuran_bpjs_tk_total} neg />
            <Line k={s.pph21_method === "pasal17" ? "PPh 21 Desember (Pasal 17)" : `PPh 21 (TER ${s.ter_category} ${s.ter_rate}%)`} v={s.pph21_amount} neg testId="detail-pph21" />
            <Line k="Kasbon / Lainnya" v={s.other_deductions} neg />
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="att" className="bg-white rounded-xl border border-slate-200 px-4">
          <AccordionTrigger data-testid="accordion-discipline" className="text-sm font-semibold">Disiplin Kehadiran</AccordionTrigger>
          <AccordionContent className="text-sm text-slate-600 space-y-1">
            <div>Poin disiplin: <b className="num">{s.late_penalty_points}</b> · Hari potong: <b className="num">{s.late_penalty_days}/25</b></div>
            <div>Potongan tunjangan kehadiran: <b className="num text-rose-600">{rp(s.late_penalty_amount)}</b></div>
            {s.late_penalty_compensation > 0 && <div>Kompensasi HRD: <b className="num">{rp(s.late_penalty_compensation)}</b></div>}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      <div className="fixed bottom-0 inset-x-0 z-40">
        <div className="max-w-md mx-auto px-4 pb-5 pt-3 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent space-y-2">
          <button data-testid="download-pdf-fab" onClick={download} disabled={busy} className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-3.5 rounded-full shadow-2xl flex items-center justify-center gap-2 transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-60">
            <Download className="h-4 w-4" /> {busy ? "Mengunduh..." : "Unduh Slip Gaji (PDF)"}
          </button>
          <div data-testid="pdf-security-badge" className="flex items-center gap-2 bg-amber-100 text-amber-900 text-xs rounded-lg px-3 py-2">
            <ShieldCheck className="h-4 w-4 shrink-0" /> File PDF dilindungi sandi 6 digit tanggal lahir Anda (DDMMYY)
          </div>
        </div>
      </div>
    </div>
  );
}
