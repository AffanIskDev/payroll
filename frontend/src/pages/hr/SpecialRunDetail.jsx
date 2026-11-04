import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronDown, ChevronLeft, DownloadCloud, FileUp, Wallet, Landmark, LockKeyhole, Save, Send, XCircle, AlertTriangle, FileText, Undo2, UserX, UserCheck } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, saveFile, blobErrMsg, downloadBlob } from "@/lib/api";
import { rp, formatDate, BULAN_NAMA } from "@/lib/format";
import { RUNS } from "@/lib/runs";
import { PageTitle, Panel, PeriodStatusChip, Btn, KpiCard, NameFilter, matchName } from "@/components/common";
import { useAuth } from "@/context/AuthContext";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

// Detail run THR / Bonus Tahunan (user 30 Okt 2026): satu baris per karyawan dengan nominalnya. Nominal dari ROSY, atau diisi
// di RUSA (menimpa ROSY). PPh 21 TIDAK dipotong di run ini (keputusan atasan 30 Okt: ditunda ke rekonsiliasi Pasal 17); slip, ajukan, approve, dan
// Batch BSI memakai jalur periode yang sama dengan gaji.
const SOURCE = { rosy: "ROSY", rusa: "RUSA" };

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
  const [gapokOpen, setGapokOpen] = useState(false);
  const [sel, setSel] = useState(() => new Set());   // employee_id yang dicentang untuk dikecualikan / disertakan
  const [multiplier, setMultiplier] = useState("1");
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
  const picked = rows.filter((r) => sel.has(r.employee_id));
  const pickedActive = picked.filter((r) => !r.excluded).map((r) => r.employee_id);
  const pickedExcluded = picked.filter((r) => r.excluded).map((r) => r.employee_id);
  const allShownPicked = shown.length > 0 && shown.every((r) => sel.has(r.employee_id));

  // slip gaji Pasal 17 (Desember / karyawan keluar) ikut dihitung ulang oleh backend setiap nominal berubah
  const recomputedNote = (d) => { if (d?.recomputed?.length) toast.info(`Slip gaji ${d.recomputed.map((b) => BULAN_NAMA[Number(b.slice(5, 7)) - 1]).join(", ")} dihitung ulang (pajak ${run.label} ikut)`); };
  const parse = (t) => (String(t).trim() === "" ? null : Number(String(t).replace(/\./g, "").replace(",", ".")));
  const save = () => act(async () => {
    const items = Object.entries(edits).map(([employee_id, t]) => ({ employee_id, nominal: parse(t) }));
    if (items.some((i) => i.nominal !== null && (Number.isNaN(i.nominal) || i.nominal < 0))) throw new Error("Ada nominal yang tidak valid");
    const { data } = await api.put(`/hr/special-runs/${pid}/amounts`, { items });
    setEdits({});
    recomputedNote(data);
  }, "Nominal disimpan & slip dihitung ulang");
  const revert = (eid) => act(() => api.put(`/hr/special-runs/${pid}/amounts`, { items: [{ employee_id: eid, nominal: null }] }), "Kembali ke nominal ROSY");
  const sync = () => act(() => api.post(`/hr/special-runs/${pid}/sync`), `Karyawan & nominal ${run.label} ditarik ulang dari ROSY`);
  const upload = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const body = new FormData();
    body.append("file", f);
    act(async () => { const { data } = await api.post(`/hr/special-runs/${pid}/import`, body); toast.info(`${data.imported} baris diimpor`); recomputedNote(data); }, null);
  };
  const setExcluded = (ids, excluded) => act(async () => {
    const { data } = await api.put(`/hr/special-runs/${pid}/excluded`, { employee_ids: ids, excluded });
    setSel(new Set());
    recomputedNote(data);
  }, excluded ? `${ids.length} karyawan dikecualikan dari ${run.label}` : `${ids.length} karyawan disertakan kembali`);
  const toggleSel = (eid) => setSel((cur) => { const n = new Set(cur); if (n.has(eid)) n.delete(eid); else n.add(eid); return n; });
  const mult = Number(String(multiplier).replace(",", "."));
  const fromGapok = async () => {
    let result = null;
    const ok = await act(async () => {
      const { data } = await api.post(`/hr/special-runs/${pid}/from-gapok`, { multiplier: mult });
      result = data;
      toast.info(`${data.filled} karyawan diisi dari gaji pokok${data.no_gapok.length ? `; ${data.no_gapok.length} tanpa gaji pokok dilewati` : ""}`);
      recomputedNote(data);
    }, null);
    if (ok) setGapokOpen(false);
    return result;
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
          {editable && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger data-testid="run-fill-menu" disabled={busy} className="w-full sm:w-auto justify-center whitespace-nowrap inline-flex items-center gap-1.5 px-4 py-2 min-h-[40px] rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 hover:border-slate-400"><Wallet className="h-4 w-4" /> Isi Nominal <ChevronDown className="h-4 w-4" /></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80">
                <DropdownMenuItem data-testid="run-sync-button" onSelect={sync} className="flex-col items-start gap-0.5 cursor-pointer">
                  <span className="flex items-center gap-2 font-semibold"><DownloadCloud className="h-4 w-4" /> Tarik dari ROSY</span>
                  <span className="text-xs text-slate-500 pl-6">Karyawan dan nominal dari ROSY. Nominal yang diisi di RUSA tetap.</span>
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="run-import-button" onSelect={() => file.current?.click()} className="flex-col items-start gap-0.5 cursor-pointer">
                  <span className="flex items-center gap-2 font-semibold"><FileUp className="h-4 w-4" /> Impor Nominal</span>
                  <span className="text-xs text-slate-500 pl-6">Berkas .xlsx / .csv berkolom nik dan nominal.</span>
                </DropdownMenuItem>
                <DropdownMenuItem data-testid="run-gapok-button" onSelect={() => setGapokOpen(true)} className="flex-col items-start gap-0.5 cursor-pointer">
                  <span className="flex items-center gap-2 font-semibold"><Wallet className="h-4 w-4" /> Ambil dari Gaji Pokok</span>
                  <span className="text-xs text-slate-500 pl-6">Semua karyawan = gaji pokok × pengali.</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <input ref={file} type="file" accept=".xlsx,.csv" className="hidden" onChange={upload} data-testid="run-import-input" />
          <Btn variant="outline" disabled={busy || !summary.slips} onClick={() => setBatchOpen(true)} data-testid="run-batch-button" className="justify-center whitespace-nowrap"><Landmark className="h-4 w-4" /> Batch Payment BSI</Btn>
          {!isManager && editable && <Btn disabled={busy || !summary.slips || blocked || dirty > 0} onClick={() => post("submit", "Diajukan ke Manager HRD")} data-testid="run-submit-button" className="justify-center whitespace-nowrap" title={dirty ? "Simpan nominal dulu" : blocked ? `Rekening ${blockers.length} karyawan belum siap` : ""}><Send className="h-4 w-4" /> Ajukan ke Manager</Btn>}
          {isManager && pending && <Btn variant="outline" disabled={busy} onClick={() => setRejectOpen(true)} data-testid="run-reject-button" className="justify-center whitespace-nowrap !border-rose-300 !text-rose-700 hover:!bg-rose-50"><XCircle className="h-4 w-4" /> Tolak</Btn>}
          {isManager && <Btn disabled={busy || locked || !summary.slips || blocked || dirty > 0} onClick={() => setApproveOpen(true)} data-testid="run-approve-button" className="justify-center whitespace-nowrap" title={dirty ? "Simpan nominal dulu" : blocked ? `Rekening ${blockers.length} karyawan belum siap` : ""}><LockKeyhole className="h-4 w-4" /> {locked ? "Sudah Dikunci" : "Lock & Approve"}</Btn>}
        </div>
      </PageTitle>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4" data-testid="run-kpis">
        <KpiCard label="Penerima" value={`${summary.slips} dari ${summary.employees}`} sub={`ROSY ${summary.from_rosy} · RUSA ${summary.from_rusa}${summary.excluded ? ` · Dikecualikan ${summary.excluded}` : ""}`} accent="brand" />
        <KpiCard label={`Total ${run.label}`} value={rp(summary.nominal)} accent="brand" />
        <KpiCard label="PPh 21" value={rp(summary.pph21)} sub="ditunda ke rekonsiliasi Pasal 17" accent="amber" />
        <KpiCard label="Total Diterima" value={rp(summary.thp)} accent="emerald" testId="run-kpi-thp" />
      </div>

      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3 flex gap-3" data-testid="run-tax-deferred-note">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <div>
          {run.label} dibayar <b>utuh tanpa potongan PPh 21</b>. Pajaknya dihitung di rekonsiliasi Pasal 17 pada slip gaji Desember, atau slip terakhir karyawan yang keluar sebelum Desember.
        </div>
      </div>
      {summary.final_tax_month && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3" data-testid="run-december-note">
          Dibayar di <b>Desember</b>: penghasilan ini ikut rekonsiliasi PPh 21 Desember (Pasal 17). Slip gaji Desember baru bisa di-approve setelah run ini di-approve.
        </div>
      )}
      {editable && !summary.slips && rows.length > 0 && (
        <div className="mb-3 rounded-lg border border-brand-200 bg-brand-50 text-slate-800 text-sm px-4 py-4" data-testid="run-source-choice">
          <div className="font-semibold mb-1">Nominal {run.label} belum terisi. Pilih sumbernya:</div>
          <div className="flex flex-wrap gap-2 mt-2">
            <Btn variant="outline" disabled={busy} onClick={() => file.current?.click()} data-testid="run-choice-import"><FileUp className="h-4 w-4" /> Impor Nominal (.xlsx / .csv)</Btn>
            <Btn disabled={busy} onClick={() => setGapokOpen(true)} data-testid="run-choice-gapok"><Wallet className="h-4 w-4" /> Ambil dari Gaji Pokok</Btn>
          </div>
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
              <Btn disabled={!dirty || busy} onClick={save} data-testid="run-save-button" title={dirty ? "" : "Aktif setelah ada nominal yang diubah"}><Save className="h-4 w-4" /> {busy && dirty ? "Menyimpan..." : "Simpan Nominal"}</Btn>
            </div>
          )}
        </div>
        {editable && picked.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 px-4 sm:px-5 py-2.5 border-b border-slate-200 bg-slate-50 text-sm" data-testid="run-selection-bar">
            <span className="text-slate-700"><b className="num">{picked.length}</b> karyawan dipilih</span>
            {pickedActive.length > 0 && <Btn variant="outline" disabled={busy || dirty > 0} onClick={() => setExcluded(pickedActive, true)} data-testid="run-exclude-button" title={dirty ? "Simpan nominal dulu" : ""}><UserX className="h-4 w-4" /> Kecualikan ({pickedActive.length})</Btn>}
            {pickedExcluded.length > 0 && <Btn variant="outline" disabled={busy || dirty > 0} onClick={() => setExcluded(pickedExcluded, false)} data-testid="run-include-button" title={dirty ? "Simpan nominal dulu" : ""}><UserCheck className="h-4 w-4" /> Sertakan kembali ({pickedExcluded.length})</Btn>}
            <button onClick={() => setSel(new Set())} className="tap text-slate-500 hover:text-slate-900 underline">Batal pilih</button>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="run-table">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                {editable && <th className="w-10 pl-4 sm:pl-5 py-3"><input type="checkbox" aria-label="Pilih semua yang tampil" data-testid="run-select-all" checked={allShownPicked} onChange={() => setSel(allShownPicked ? new Set() : new Set(shown.map((r) => r.employee_id)))} /></th>}
                <th className="text-left px-4 sm:px-5 py-3">Karyawan</th>
                <th className="text-left px-3 py-3">Sumber</th>
                <th className="text-right px-3 py-3">Nominal {run.label}</th>
                <th className="text-right px-3 py-3">PPh 21</th>
                <th className="text-right px-3 py-3">Total Diterima</th>
                <th className="text-left px-3 py-3">Pajak</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((r) => {
                const typed = edits[r.employee_id];
                const value = typed !== undefined ? typed : r.nominal ? String(Math.round(r.nominal)) : "";
                return (
                  <tr key={r.employee_id} className={r.excluded ? "bg-slate-50 text-slate-400" : r.slip ? "hover:bg-slate-50" : "text-slate-400"} data-testid={`run-row-${r.nik}`}>
                    {editable && <td className="w-10 pl-4 sm:pl-5 py-2.5"><input type="checkbox" aria-label={`Pilih ${r.name}`} data-testid={`run-select-${r.nik}`} checked={sel.has(r.employee_id)} onChange={() => toggleSel(r.employee_id)} /></td>}
                    <td className="px-4 sm:px-5 py-2.5"><div className="font-semibold text-slate-900">{r.name}</div><div className="text-xs text-slate-500 num">{r.nik}{r.department ? ` · ${r.department}` : ""}</div></td>
                    <td className="px-3 py-2.5 text-xs">
                      {r.excluded ? <span className="rounded-full px-2 py-0.5 font-semibold bg-amber-50 text-amber-800" data-testid={`run-excluded-${r.nik}`}>Dikecualikan</span> : r.source ? <span className={`rounded-full px-2 py-0.5 font-semibold ${r.source === "rusa" ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-600"}`}>{SOURCE[r.source]}</span> : <span className="text-slate-400">—</span>}
                      {r.source === "rusa" && r.rosy_nominal ? <div className="text-slate-500 mt-0.5">ROSY {rp(r.rosy_nominal)}</div> : null}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {editable
                        ? <input inputMode="numeric" disabled={r.excluded} aria-label={`Nominal ${run.label} ${r.name}`} data-testid={`run-input-${r.nik}`} value={value} placeholder="0"
                            onChange={(e) => setEdits({ ...edits, [r.employee_id]: e.target.value })}
                            className={`w-36 border rounded-md px-2 py-1.5 text-right num text-sm disabled:bg-slate-100 disabled:text-slate-400 ${typed !== undefined ? "border-amber-400 bg-amber-50" : "border-slate-300"}`} />
                        : <span className="num">{rp(r.nominal)}</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right num text-slate-700">{r.slip ? rp(r.slip.pph21_withheld) : "-"}</td>
                    <td className="px-3 py-2.5 text-right num font-semibold">{r.slip ? rp(r.slip.take_home_pay) : "-"}</td>
                    <td className="px-3 py-2.5 text-xs text-slate-500">{r.slip ? "Ditunda ke Pasal 17" : r.excluded ? "Tidak dapat " + run.label : ""}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {editable && r.source === "rusa" && r.rosy_nominal ? <button onClick={() => revert(r.employee_id)} title="Kembali ke nominal ROSY" className="tap p-1 rounded text-slate-500 hover:bg-slate-100 align-middle" data-testid={`run-revert-${r.nik}`}><Undo2 className="h-4 w-4" /></button> : null}
                      {r.slip && <button onClick={() => downloadBlob(`/hr/periods/${pid}/employees/${r.employee_id}/pdf`, `${run.label}-${r.nik}.pdf`, true).catch((e) => toast.error(errMsg(e)))} title="Pratinjau slip PDF" className="tap p-1 rounded text-brand-700 hover:bg-brand-50 align-middle" data-testid={`run-pdf-${r.nik}`}><FileText className="h-4 w-4" /></button>}
                    </td>
                  </tr>
                );
              })}
              {!shown.length && <tr><td colSpan={editable ? 8 : 7} className="px-5 py-10 text-center text-slate-500">{rows.length ? "Tidak ada yang cocok dengan filter." : "Belum ada karyawan. Klik “Tarik dari ROSY”."}</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      <Dialog open={gapokOpen} onOpenChange={(o) => !busy && setGapokOpen(o)}>
        <DialogContent data-testid="run-gapok-dialog">
          <DialogHeader><DialogTitle>Ambil {run.label} dari gaji pokok</DialogTitle><DialogDescription>Nominal tiap karyawan = gaji pokok kontrak × pengali. Tanpa prorata masa kerja; hasilnya masih bisa diubah per baris.</DialogDescription></DialogHeader>
          <label className="text-sm text-slate-700 flex items-center gap-2">Pengali
            <input inputMode="decimal" value={multiplier} onChange={(e) => setMultiplier(e.target.value)} data-testid="run-gapok-multiplier" className="w-24 border border-slate-300 rounded-md px-2 py-1.5 text-right num" /> × gaji pokok
          </label>
          {summary.from_rusa > 0 && <p className="text-sm text-amber-800">Nominal yang sudah diisi / diimpor di RUSA ({summary.from_rusa} karyawan) akan <b>ditimpa</b>.</p>}
          <div className="flex justify-end gap-2">
            <Btn variant="outline" disabled={busy} onClick={() => setGapokOpen(false)}>Batal</Btn>
            <Btn disabled={busy || !(mult > 0 && mult <= 24)} onClick={fromGapok} data-testid="run-gapok-confirm"><Wallet className="h-4 w-4" /> {busy ? "Mengisi..." : "Isi Nominal"}</Btn>
          </div>
        </DialogContent>
      </Dialog>
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
