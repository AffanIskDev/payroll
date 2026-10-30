import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, DownloadCloud, FileUp, Landmark, LockKeyhole, Save, Send, XCircle, AlertTriangle, FileText, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg, downloadBlob } from "@/lib/api";
import { rp, formatDate, BULAN_NAMA } from "@/lib/format";
import { RUNS } from "@/lib/runs";
import { PageTitle, Panel, PeriodStatusChip, Btn, KpiCard, NameFilter, matchName } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Detail run THR / Bonus Tahunan (user 30 Okt 2026): satu baris per karyawan dengan nominalnya. Nominal dari ROSY, atau diisi
// di RUSA (menimpa ROSY). PPh 21 = selisih TER atas gaji bulan dibayar (engine.special_tax); slip, ajukan, approve, dan
// Batch BSI memakai jalur periode yang sama dengan gaji.
const SOURCE = { rosy: "ROSY", rusa: "RUSA" };
const BASE_NOTE = { slip_bulan_ini: "gaji bulan ini", tidak_ada: "tanpa dasar gaji" };
const baseNote = (src) => BASE_NOTE[src] || (src?.startsWith("slip_terakhir") ? `perkiraan: ${src.split(":")[1]}` : "-");

export default function SpecialRunDetail({ runType }) {
  const { pid } = useParams();
  return <Detail key={pid} pid={pid} runType={runType} />;
}

function Detail({ pid, runType }) {
  const run = RUNS[runType];
  const { user } = useAuth();
  const isManager = user?.role === "manager_hrd";
  const [d, setD] = useState(null);
  const [edits, setEdits] = useState({});   // employee_id -> teks yang diketik (belum disimpan)
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchProblems, setBatchProblems] = useState(null);
  const [reason, setReason] = useState("");
  const file = useRef(null);
  const load = useCallback(() => api.get(`/hr/special-runs/${pid}`).then((r) => setD(r.data)), [pid]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, msg) => {
    setBusy(true);
    try { await fn(); if (msg) toast.success(msg); await load(); return true; } catch (e) { toast.error(await blobErrMsg(e)); return false; } finally { setBusy(false); }
  };
  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, rows, summary, bank_blockers: blockers } = d;
  const editable = ["draft", "revision"].includes(period.status);
  const pending = period.status === "pending_approval";
  const locked = period.status === "approved";
  const blocked = blockers.length > 0 && !locked;
  const taxMonth = `${BULAN_NAMA[Number(period.bulan.slice(5, 7)) - 1]} ${period.bulan.slice(0, 4)}`;
  const dirty = Object.keys(edits).length;
  const shown = rows.filter((r) => matchName(`${r.name} ${r.nik}`, q));

  const parse = (t) => (String(t).trim() === "" ? null : Number(String(t).replace(/\./g, "").replace(",", ".")));
  const save = () => act(async () => {
    const items = Object.entries(edits).map(([employee_id, t]) => ({ employee_id, nominal: parse(t) }));
    if (items.some((i) => i.nominal !== null && (Number.isNaN(i.nominal) || i.nominal < 0))) throw new Error("Ada nominal yang tidak valid");
    await api.put(`/hr/special-runs/${pid}/amounts`, { items });
    setEdits({});
  }, "Nominal disimpan & slip dihitung ulang");
  const revert = (eid) => act(() => api.put(`/hr/special-runs/${pid}/amounts`, { items: [{ employee_id: eid, nominal: null }] }), "Kembali ke nominal ROSY");
  const sync = () => act(() => api.post(`/hr/special-runs/${pid}/sync`), `Karyawan & nominal ${run.label} ditarik ulang dari ROSY`);
  const upload = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const body = new FormData();
    body.append("file", f);
    act(async () => { const { data } = await api.post(`/hr/special-runs/${pid}/import`, body); toast.info(`${data.imported} baris diimpor`); }, null);
  };
  const post = (path, msg, body) => act(() => api.post(`/hr/periods/${pid}/${path}`, body), msg);
  const exportBatch = async () => {
    setBusy(true);
    try {
      const h = await saveFile("post", `/hr/periods/${pid}/export-batch-bsi`, "BatchPayment.txt");
      setBatchOpen(false);
      toast.success(`Berkas Batch Payment diunduh: ${h["x-exported-count"]} transfer, total ${rp(h["x-total-amount"])}`);
    } catch (e) {
      let body = null;
      if (e?.response?.data instanceof Blob) { try { body = JSON.parse(await e.response.data.text()); } catch { body = null; } }
      if (body?.problems?.length) { setBatchOpen(false); setBatchProblems(body.problems); } else toast.error(typeof body?.detail === "string" ? body.detail : errMsg(e));
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="special-run-detail">
      <Link to={run.base} className="tap inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-3"><ChevronLeft className="h-4 w-4" /> Semua run {run.label}</Link>
      <PageTitle title={`${run.label}: ${period.title}`} titleExtra={<PeriodStatusChip status={period.status} testId="run-status-badge" />}
        subtitle={<>
          <span className="block">Dibayar: <span className="text-slate-700">{formatDate(period.payment_date)}</span><span className="mx-2 text-slate-300" aria-hidden="true">|</span>Masa pajak: <span className="text-slate-700" data-testid="run-tax-month">{taxMonth}</span></span>
          <span className="block">Sinkron ROSY terakhir: <span className="text-slate-700">{period.last_sync_at ? new Date(period.last_sync_at).toLocaleString("id-ID") : "belum pernah"}</span></span>
        </>}>
        <div className="flex w-full sm:w-auto flex-col sm:flex-row sm:flex-wrap gap-2" data-testid="run-actions">
          {editable && <Btn variant="outline" disabled={busy} onClick={sync} data-testid="run-sync-button" className="justify-center whitespace-nowrap" title="Menarik ulang karyawan dan nominal dari ROSY. Nominal yang diisi di RUSA tetap."><DownloadCloud className="h-4 w-4" /> Tarik dari ROSY</Btn>}
          {editable && <Btn variant="outline" disabled={busy} onClick={() => file.current?.click()} data-testid="run-import-button" className="justify-center whitespace-nowrap" title="Berkas .xlsx / .csv berkolom nik dan nominal"><FileUp className="h-4 w-4" /> Impor Nominal</Btn>}
          <input ref={file} type="file" accept=".xlsx,.csv" className="hidden" onChange={upload} data-testid="run-import-input" />
          <Btn variant="outline" disabled={busy || !summary.slips} onClick={() => setBatchOpen(true)} data-testid="run-batch-button" className="justify-center whitespace-nowrap"><Landmark className="h-4 w-4" /> Batch Payment BSI</Btn>
          {!isManager && editable && <Btn disabled={busy || !summary.slips || blocked || dirty > 0} onClick={() => post("submit", "Diajukan ke Manager HRD")} data-testid="run-submit-button" className="justify-center whitespace-nowrap" title={dirty ? "Simpan nominal dulu" : blocked ? `Rekening ${blockers.length} karyawan belum siap` : ""}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
          {isManager && pending && <Btn variant="outline" disabled={busy} onClick={() => setRejectOpen(true)} data-testid="run-reject-button" className="justify-center whitespace-nowrap !border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak</Btn>}
          {isManager && <Btn disabled={busy || locked || !summary.slips || blocked || dirty > 0} onClick={() => setApproveOpen(true)} data-testid="run-approve-button" className="justify-center whitespace-nowrap" title={dirty ? "Simpan nominal dulu" : blocked ? `Rekening ${blockers.length} karyawan belum siap` : ""}><LockKeyhole className="h-4 w-4" /> {locked ? "Sudah Dikunci" : "Lock & Approve"}</Btn>}
        </div>
      </PageTitle>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4" data-testid="run-kpis">
        <KpiCard label="Penerima" value={`${summary.slips} dari ${summary.employees}`} sub={`ROSY ${summary.from_rosy} · RUSA ${summary.from_rusa}`} accent="brand" />
        <KpiCard label={`Total ${run.label}`} value={rp(summary.nominal)} accent="brand" />
        <KpiCard label="PPh 21" value={rp(summary.pph21)} sub={`TER atas gaji ${taxMonth} + ${run.label}`} accent="amber" />
        <KpiCard label="Total Diterima" value={rp(summary.thp)} accent="emerald" testId="run-kpi-thp" />
      </div>

      {(summary.baseline_estimated > 0 || summary.baseline_none > 0) && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3 flex gap-3" data-testid="run-baseline-note">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            PPh 21 dihitung dari selisih TER atas <b>gaji {taxMonth}</b> + {run.label}. Slip gaji {taxMonth} {summary.baseline_exact ? `baru ada untuk ${summary.baseline_exact} karyawan; ` : "belum ada; "}
            {summary.baseline_estimated > 0 && <><b>{summary.baseline_estimated}</b> karyawan memakai slip gaji terakhir sebagai perkiraan. </>}
            {summary.baseline_none > 0 && <><b>{summary.baseline_none}</b> karyawan belum punya slip gaji sama sekali (dipajaki atas {run.label} saja). </>}
            Selisihnya dibereskan di PPh 21 Desember (Pasal 17).
          </div>
        </div>
      )}
      {summary.final_tax_month && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3" data-testid="run-december-note">
          Dibayar di <b>Desember</b>: penghasilan ini ikut rekonsiliasi PPh 21 Desember (Pasal 17). Slip gaji Desember baru bisa di-approve setelah run ini di-approve.
        </div>
      )}
      {blocked && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3" data-testid="run-bank-blockers">
          Rekening belum siap dibayar lewat BSI: <b>{blockers.map((b) => b.name).join(", ")}</b>. Lengkapi di ROSY HRD (Ubah Karyawan), lalu “Tarik dari ROSY”.
        </div>
      )}

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 sm:px-5 py-3 border-b border-slate-200">
          <NameFilter value={q} onChange={setQ} testId="run-name-filter" />
          {editable && (
            <div className="flex items-center gap-2">
              {dirty > 0 && <span className="text-sm text-amber-700" data-testid="run-dirty-note">{dirty} baris belum disimpan</span>}
              <Btn variant="outline" disabled={!dirty || busy} onClick={() => setEdits({})} data-testid="run-discard-button">Batalkan</Btn>
              <Btn disabled={!dirty || busy} onClick={save} data-testid="run-save-button"><Save className="h-4 w-4" /> Simpan Nominal</Btn>
            </div>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="run-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="text-left px-4 sm:px-5 py-3">Karyawan</th>
                <th className="text-left px-3 py-3">Sumber</th>
                <th className="text-right px-3 py-3">Nominal {run.label}</th>
                <th className="text-right px-3 py-3">PPh 21</th>
                <th className="text-right px-3 py-3">Total Diterima</th>
                <th className="text-left px-3 py-3">Dasar Pajak</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((r) => {
                const typed = edits[r.employee_id];
                const value = typed !== undefined ? typed : r.nominal ? String(Math.round(r.nominal)) : "";
                return (
                  <tr key={r.employee_id} className={r.slip ? "hover:bg-slate-50" : "text-slate-400"} data-testid={`run-row-${r.nik}`}>
                    <td className="px-4 sm:px-5 py-2.5"><div className="font-semibold text-slate-900">{r.name}</div><div className="text-xs text-slate-500 num">{r.nik}{r.department ? ` · ${r.department}` : ""}</div></td>
                    <td className="px-3 py-2.5 text-xs">
                      {r.source ? <span className={`rounded-full px-2 py-0.5 font-semibold ${r.source === "rusa" ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-600"}`}>{SOURCE[r.source]}</span> : <span className="text-slate-400">—</span>}
                      {r.source === "rusa" && r.rosy_nominal ? <div className="text-slate-500 mt-0.5">ROSY {rp(r.rosy_nominal)}</div> : null}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {editable
                        ? <input inputMode="numeric" aria-label={`Nominal ${run.label} ${r.name}`} data-testid={`run-input-${r.nik}`} value={value} placeholder="0"
                            onChange={(e) => setEdits({ ...edits, [r.employee_id]: e.target.value })}
                            className={`w-36 border rounded-md px-2 py-1.5 text-right num text-sm ${typed !== undefined ? "border-amber-400 bg-amber-50" : "border-slate-300"}`} />
                        : <span className="num">{rp(r.nominal)}</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right num text-slate-700">{r.slip ? rp(r.slip.pph21_withheld) : "-"}</td>
                    <td className="px-3 py-2.5 text-right num font-semibold">{r.slip ? rp(r.slip.take_home_pay) : "-"}</td>
                    <td className="px-3 py-2.5 text-xs text-slate-500">{r.slip ? <>{baseNote(r.slip.special_tax?.baseline_source)}<div className="num">TER {r.slip.ter_category} {r.slip.special_tax?.total_rate}%</div></> : ""}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {editable && r.source === "rusa" && r.rosy_nominal ? <button onClick={() => revert(r.employee_id)} title="Kembali ke nominal ROSY" className="tap p-1 rounded text-slate-500 hover:bg-slate-100 align-middle" data-testid={`run-revert-${r.nik}`}><Undo2 className="h-4 w-4" /></button> : null}
                      {r.slip && <button onClick={() => downloadBlob(`/hr/periods/${pid}/employees/${r.employee_id}/pdf`, `${run.label}-${r.nik}.pdf`, true).catch((e) => toast.error(errMsg(e)))} title="Pratinjau slip PDF" className="tap p-1 rounded text-brand-700 hover:bg-brand-50 align-middle" data-testid={`run-pdf-${r.nik}`}><FileText className="h-4 w-4" /></button>}
                    </td>
                  </tr>
                );
              })}
              {!shown.length && <tr><td colSpan={7} className="px-5 py-10 text-center text-slate-500">{rows.length ? "Tidak ada yang cocok dengan filter." : "Belum ada karyawan. Klik “Tarik dari ROSY”."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent data-testid="run-reject-dialog">
          <DialogHeader><DialogTitle>Tolak {period.period_name}</DialogTitle><DialogDescription>Run dikembalikan ke Supervisor HRD untuk dikoreksi. Tuliskan alasannya.</DialogDescription></DialogHeader>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} data-testid="run-reject-reason" className="w-full border border-slate-300 rounded-md p-3 text-sm min-h-[90px]" />
          <div className="flex justify-end gap-2">
            <Btn variant="outline" onClick={() => setRejectOpen(false)}>Batal</Btn>
            <Btn disabled={busy || reason.trim().length < 5} data-testid="run-reject-confirm" className="!bg-rose-600 hover:!bg-rose-700"
              onClick={async () => { if (await post("reject", "Run dikembalikan ke Supervisor HRD", { reason })) { setRejectOpen(false); setReason(""); } }}><XCircle className="h-4 w-4" /> Tolak & Kembalikan</Btn>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={approveOpen} onOpenChange={(o) => !busy && setApproveOpen(o)}>
        <DialogContent data-testid="run-approve-dialog">
          <DialogHeader><DialogTitle>Lock & Approve {period.period_name}?</DialogTitle><DialogDescription><span className="num">{summary.slips}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(summary.thp)}</b></DialogDescription></DialogHeader>
          <p className="text-sm text-slate-600">Semua slip <b>dikunci dan tidak bisa diubah lagi</b>, lalu dikirim ke aplikasi Rumatku karyawan.</p>
          <div className="flex justify-end gap-2">
            <Btn variant="outline" disabled={busy} onClick={() => setApproveOpen(false)}>Batal</Btn>
            <Btn variant="success" disabled={busy} data-testid="run-approve-confirm" onClick={async () => { if (await post("approve-all", "Semua slip dikunci & di-approve")) setApproveOpen(false); }}><LockKeyhole className="h-4 w-4" /> {busy ? "Mengunci..." : "Ya, Lock & Approve"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={batchOpen} onOpenChange={(o) => !busy && setBatchOpen(o)}>
        <DialogContent data-testid="run-batch-dialog">
          <DialogHeader><DialogTitle>Buat berkas Batch Payment BSI?</DialogTitle><DialogDescription>{period.period_name} · <span className="num">{summary.slips}</span> slip · Total Diterima <b className="num whitespace-nowrap">{rp(summary.thp)}</b></DialogDescription></DialogHeader>
          <div className="flex justify-end gap-2">
            <Btn variant="outline" disabled={busy} onClick={() => setBatchOpen(false)}>Batal</Btn>
            <Btn variant="success" disabled={busy} onClick={exportBatch} data-testid="run-batch-confirm"><Landmark className="h-4 w-4" /> {busy ? "Menyiapkan berkas..." : "Ya, Buat Berkas"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={!!batchProblems} onOpenChange={(o) => !o && setBatchProblems(null)}>
        <DialogContent data-testid="run-batch-problems">
          <DialogHeader><DialogTitle>Berkas tidak dibuat</DialogTitle><DialogDescription>{batchProblems?.length} data harus dibetulkan dulu di ROSY.</DialogDescription></DialogHeader>
          <ul className="text-sm max-h-64 overflow-y-auto space-y-1">{batchProblems?.map((p, i) => <li key={i}><b>{p.name}</b> — {p.kind}: {p.note}</li>)}</ul>
          <div className="flex justify-end"><Btn onClick={() => setBatchProblems(null)}>Mengerti</Btn></div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
