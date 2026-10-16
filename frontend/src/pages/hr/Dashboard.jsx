import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users, UserPlus, UserMinus, UserX, AlertTriangle, Wallet, Receipt, HeartPulse, HardHat, ArrowRight, BellRing, XCircle, ChevronDown, LockKeyhole, TrendingUp, TrendingDown, Minus, Hourglass, ClipboardList, Landmark } from "lucide-react";
import { api } from "@/lib/api";
import { rp, PERIOD_STATUS, DATA_ISSUE_LABELS, formatDate, formatDateRange, localIso } from "@/lib/format";
import { PageTitle, Panel, StatusBadge, PeriodStatusChip, AccentBody } from "@/components/common";

// kartu angka beraksen (garis warna kiri + angka berwarna; desain RUMAT), sama dengan kartu di halaman periode.
// children = perbandingan dengan periode sebelumnya (user 14 Okt 2026)
const Stat = ({ icon, label, value, hint, accent, dim, big, testId, wide, children }) => (
  // wide: kartu pertama melebar 2 kolom di tablet/laptop kecil supaya 5 kartu mengisi baris tanpa sisa
  <div className={`relative overflow-hidden ${wide ? "sm:col-span-2 xl:col-span-1" : ""} bg-white border border-slate-200 rounded-xl pl-5 pr-4 py-4 shadow-sm fade-up`}>
    <AccentBody icon={icon} label={label} value={value} sub={hint} accent={accent} dim={dim} big={big} valueTestId={testId} />
    {children}
  </div>
);

// Perbandingan dengan periode sebelumnya (user 14 Okt 2026): naik / turun dan berapa persen. `d` = {prev, diff, pct} dari
// backend (compare); tidak tampil bila periode sebelumnya tidak ada atau kosong (pct null). `orang` = kartu jumlah karyawan
// (tampilkan selisih orang); kartu rupiah menampilkan nilai periode sebelumnya & selisihnya di tooltip.
const Delta = ({ d, prev, orang, testId }) => {
  if (!d || d.pct == null) return null;
  const dir = d.diff > 0 ? "up" : d.diff < 0 ? "down" : "same";
  const Icon = { up: TrendingUp, down: TrendingDown, same: Minus }[dir];
  const tone = { up: "text-emerald-600", down: "text-rose-600", same: "text-slate-500" }[dir];
  const abs = Math.abs(d.pct);
  const pct = abs < 0.1 && dir !== "same" ? "< 0,1%" : `${abs.toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  const sign = d.diff > 0 ? "+" : "−";
  const title = orang ? `${prev}: ${d.prev} orang` : `${prev}: ${rp(d.prev)}${dir === "same" ? "" : ` · selisih ${sign}${rp(Math.abs(d.diff))}`}`;
  return (
    <div data-testid={testId} data-dir={dir} title={title} className="mt-1 text-xs">
      <span className={`inline-flex items-center gap-1 font-semibold ${tone}`}>
        <Icon className="h-3.5 w-3.5" />
        {dir === "same" ? "Sama" : `${dir === "up" ? "Naik" : "Turun"} ${pct}`}
        {orang && dir !== "same" ? ` (${sign}${Math.abs(d.diff)} orang)` : ""}
      </span>
      <div className="text-slate-500">{dir === "same" ? "dengan" : "dari"} {prev}</div>
    </div>
  );
};

const Notice = ({ n }) => {
  const rejected = n.kind === "rejected";
  return (
    <Link to={`/hr-manager/payroll/${n.period_id}`} data-testid={`notification-${n.period_id}`} className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors fade-up ${rejected ? "bg-rose-50 border-rose-200 hover:bg-rose-100" : "bg-amber-50 border-amber-200 hover:bg-amber-100"}`}>
      {rejected ? <XCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" /> : <BellRing className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />}
      <div className="text-sm flex-1">
        <div className={`font-semibold ${rejected ? "text-rose-800" : "text-amber-900"}`}>{rejected ? `Draft ${n.period_name} ditolak — perlu dikoreksi` : `Draft ${n.period_name} diajukan — menunggu approval Anda`}</div>
        <div className="text-xs text-slate-600 mt-0.5">oleh {n.by} · <span className="num">{n.at ? new Date(n.at).toLocaleString("id-ID") : "-"}</span></div>
        {n.reason && <div className="text-xs text-rose-700 mt-1">Alasan: {n.reason}</div>}
      </div>
      <ArrowRight className="h-4 w-4 text-slate-400 mt-1" />
    </Link>
  );
};

// Kelompok "Perlu Ditinjau" (user 10 Okt 2026): siapa yang keluar/masuk, tidak digaji, digaji tidak penuh, dan data.
// 13 Okt 2026: "Absensi perlu dicek" dibuang; "Tidak ikut digaji" bukan lagi karyawan tanpa Kontrak Gaji.
// 14 Okt 2026: "Tidak ikut digaji" = unpaid saja (sama dgn kartunya); cuti melahirkan tetap digaji (gaji pokok), jadi
// masuk "Gaji tidak penuh".
// 14 Okt 2026: "Karyawan keluar" = yang sudah tidak aktif di periode ini (tanggal keluar dari ROSY); label lama "keluar / tidak
// dikirim ROSY lagi" diganti atas permintaan user (kartu & keterangan kelompok ini).
// 14 Okt 2026: "Rekening belum siap" paling atas — no. rekening / nama di rekening kosong atau bukan BSI memblokir Ajukan ke Manager & Lock & Approve.
const GROUP_INFO = {
  bank: "Ajukan ke Manager dan Lock & Approve diblokir sampai No. Rekening, Nama di Rekening, dan Bank (harus BSI) lengkap di ROSY",
  left: "Sudah tidak aktif di periode ini (tanggal keluar dari ROSY), atau ada di periode sebelumnya tapi tidak ada di periode ini",
  new: "Mulai bekerja di periode ini — cek Kontrak Gaji & slip pertamanya",
  not_paid: "Unpaid / cuti di luar tanggungan — upah & tunjangan Rp 0",
  partial: "Masuk atau keluar di tengah periode, cuti melahirkan (sepanjang periode: hanya gaji pokok), sakit berkepanjangan",
  data: "Data karyawan di ROSY yang belum lengkap — selain rekening, tidak menghalangi payroll",
};

// Gaya tiap kelompok (user 14 Okt 2026: daftar yang dibuka harus menjorok di bawah judul grupnya, dengan garis & warna
// kelompok, dan detailnya disorot, bukan teks abu-abu kecil yang rata dengan judul). Kelas ditulis utuh supaya Tailwind
// membacanya.
const GROUP_STYLE = {
  bank: { icon: Landmark, badge: "bg-rose-100 text-rose-700", iconBox: "bg-rose-50 text-rose-600 border-rose-100", bar: "border-l-rose-500", dot: "bg-rose-500", chip: "bg-rose-50 text-rose-800 border-rose-200" },
  left: { icon: UserMinus, badge: "bg-rose-100 text-rose-700", iconBox: "bg-rose-50 text-rose-600 border-rose-100", bar: "border-l-rose-400", dot: "bg-rose-500", chip: "bg-rose-50 text-rose-800 border-rose-200" },
  new: { icon: UserPlus, badge: "bg-brand-100 text-brand-800", iconBox: "bg-brand-50 text-brand-700 border-brand-100", bar: "border-l-brand-400", dot: "bg-brand-500", chip: "bg-brand-50 text-brand-800 border-brand-200" },
  not_paid: { icon: UserX, badge: "bg-amber-100 text-amber-800", iconBox: "bg-amber-50 text-amber-600 border-amber-100", bar: "border-l-amber-400", dot: "bg-amber-500", chip: "bg-amber-50 text-amber-900 border-amber-200" },
  partial: { icon: Hourglass, badge: "bg-amber-100 text-amber-800", iconBox: "bg-amber-50 text-amber-600 border-amber-100", bar: "border-l-amber-400", dot: "bg-amber-500", chip: "bg-amber-50 text-amber-900 border-amber-200" },
  data: { icon: ClipboardList, badge: "bg-slate-200 text-slate-700", iconBox: "bg-slate-100 text-slate-600 border-slate-200", bar: "border-l-slate-400", dot: "bg-slate-400", chip: "bg-white text-slate-700 border-slate-300" },
};
const DEFAULT_STYLE = GROUP_STYLE.data;

// Catatan backend "fakta — akibat/tindakan" dipecah dua: fakta di depan (titik warna kelompok), keterangannya disorot sebagai
// label — mis. "cuti melahirkan 11 hari" + [dibayarkan gaji pokok saja], "masuk 14 September" + [cek prorata]
const Detail = ({ note, st }) => {
  const [fact, ...rest] = String(note || "").split(" — ");
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px]" data-testid="review-note">
      <span className="inline-flex items-center gap-1.5 text-slate-700">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${st.dot}`} />{fact}
      </span>
      {rest.length > 0 && <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${st.chip}`}>{rest.join(" — ")}</span>}
    </div>
  );
};

const ReviewGroup = ({ g, pid, open, onToggle }) => {
  const info = GROUP_INFO[g.key] || "";
  const st = GROUP_STYLE[g.key] || DEFAULT_STYLE;
  const Icon = st.icon;
  const count = g.items.length;
  return (
    <div className={`border-b border-slate-100 last:border-0 ${open ? "bg-slate-50/40" : ""}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={`review-list-${g.key}`} data-testid={`review-group-${g.key}`} className="w-full flex items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-slate-50">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${count ? st.iconBox : "bg-slate-50 text-slate-300 border-slate-100"}`}><Icon className="h-[18px] w-[18px]" /></span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-900">{g.title}</span>
          <span className="block text-[13px] leading-snug text-slate-600">{info}</span>
        </span>
        <span className={`num inline-flex min-w-[2.25rem] justify-center rounded-full px-2.5 py-0.5 text-sm font-bold ${count ? st.badge : "bg-slate-100 text-slate-400"}`} data-testid={`review-count-${g.key}`}>{count}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        // menjorok: kiri daftar sejajar dengan teks judul (ikon 36 px + jarak 12 px + padding 20 px); garis tebal berwarna kelompok di kirinya
        <div className="pb-3.5 pl-8 pr-5 sm:pl-[4.25rem]">
          <div className={`overflow-hidden rounded-md border border-slate-200 border-l-[3px] ${count ? st.bar : "border-l-slate-300"} bg-white shadow-sm`}>
            <ul id={`review-list-${g.key}`} data-testid={`review-list-${g.key}`} className="max-h-[26rem] divide-y divide-slate-100 overflow-y-auto">
              {g.items.map((it, i) => (
                <li key={`${it.employee_id || it.name}-${i}`} className="flex items-start justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-slate-50" data-testid="review-item">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span className="text-sm font-semibold text-slate-900">{it.name}</span>
                      <span className="num text-xs text-slate-500">{it.nik}</span>
                    </div>
                    {g.key === "data" ? (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {(it.issues || []).map((x) => <span key={x} className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${st.chip}`}>{DATA_ISSUE_LABELS[x] || x}</span>)}
                      </div>
                    ) : <Detail note={it.note} st={st} />}
                  </div>
                  {it.has_slip && (
                    <Link to={`/hr-manager/payroll/${pid}/employee/${it.employee_id}`} className="tap inline-flex shrink-0 items-center gap-1 rounded-md border border-brand-200 bg-white px-2.5 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-50 whitespace-nowrap">
                      Review <ArrowRight className="h-3 w-3" />
                    </Link>
                  )}
                </li>
              ))}
              {!count && <li className="px-4 py-3 text-sm text-slate-500">Tidak ada karyawan di kelompok ini.</li>}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};

export default function Dashboard() {
  const [notes, setNotes] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [d, setD] = useState(null);
  const [open, setOpen] = useState({});

  const load = useCallback((pid) => api.get("/hr/dashboard/employees", { params: pid ? { pid } : {} }).then((r) => setD(r.data)), []);
  const loadLists = useCallback(() => {
    api.get("/hr/periods").then((r) => setPeriods(r.data));
    api.get("/hr/notifications").then((r) => setNotes(r.data));
  }, []);
  useEffect(() => { load(); loadLists(); }, [load, loadLists]);

  if (!d) return <div className="text-sm text-slate-500">Memuat...</div>;
  const { period, counts, groups, payroll, compare } = d;
  const prevName = compare?.period_name;
  const editable = period && ["draft", "revision"].includes(period.status);

  // Tombol "Fetch Data Terbaru" ada di halaman periode (menu Payroll), bukan di sini (user 13 Okt 2026);
  // Dashboard hanya menampilkan kapan sinkron terakhir
  const lastSyncDay = period?.last_sync_at ? localIso(new Date(period.last_sync_at)) : null;
  const syncedMidPeriod = editable && lastSyncDay && period.start_date <= lastSyncDay && lastSyncDay <= period.end_date;

  return (
    <div data-testid="hr-dashboard">
      <PageTitle title="Dashboard Payroll" subtitle={period ? <><span className="block">{formatDateRange(period.start_date, period.end_date)}</span><span className="block" data-testid="dashboard-sync-status">Sinkron terakhir: {period.last_sync_at ? new Date(period.last_sync_at).toLocaleString("id-ID") : "belum pernah"}{syncedMidPeriod && <span className="text-amber-700" data-testid="dashboard-sync-midperiod"> · diambil saat periode berjalan, alfa {formatDate(lastSyncDay)} belum final</span>}</span></> : "Belum ada periode — buat di menu Payroll"}>
        {/* "Periode [pilihan] [status]": status milik periode yang dipilih, jadi duduk di sampingnya sebagai lencana yang sama
            dengan halaman periode (user 15 Okt 2026; dulu "Status: Draft" di depan pilihan) */}
        {periods.length > 0 && (
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2" data-testid="dashboard-period-picker">
            <label htmlFor="dashboard-period-select" className="text-sm text-slate-500">Periode</label>
            <select id="dashboard-period-select" data-testid="dashboard-period-select" value={period?.id || ""} onChange={(e) => load(e.target.value)} className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
              {periods.map((p) => <option key={p.id} value={p.id}>{p.period_name}</option>)}
            </select>
            {period && <PeriodStatusChip status={period.status} testId="dashboard-period-status" />}
          </div>
        )}
      </PageTitle>
      {period?.last_sync_error && (
        <div className="mb-4 flex gap-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-md px-4 py-3 text-sm" data-testid="dashboard-sync-error">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>Sinkron dari ROSY terakhir gagal: {period.last_sync_error}. Buka <Link to={`/hr-manager/payroll/${period.id}`} className="font-semibold underline">halaman periode {period.period_name}</Link>, lalu klik "Fetch Data Terbaru" untuk mencoba lagi.</span>
        </div>
      )}
      {period && (
        // kartu nominal di paling atas (user 13 Okt 2026); angka rupiah butuh lebar: satu kolom di HP supaya tidak meluber dari kartu (12 Okt 2026)
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
          <Stat wide icon={Wallet} label="Total THP" big accent="emerald" value={rp(payroll.total_thp)} hint={`${payroll.slips} slip${period.payment_date ? ` · transfer ${formatDate(period.payment_date)}` : ""}`} testId="stat-total-thp">
            <Delta d={compare?.total_thp} prev={prevName} testId="delta-total-thp" />
          </Stat>
          <Stat icon={Receipt} label="Total PPh 21" big accent="brand" value={rp(payroll.total_pph21)} hint="TER bulanan · PP 58/2023" testId="stat-total-pph21">
            <Delta d={compare?.total_pph21} prev={prevName} testId="delta-total-pph21" />
          </Stat>
          <Stat icon={HeartPulse} label="BPJS Kesehatan" big accent="brand" value={rp(payroll.total_bpjs_kes)} hint="setoran periode ini" testId="stat-total-bpjs-kes">
            <Delta d={compare?.total_bpjs_kes} prev={prevName} testId="delta-total-bpjs-kes" />
          </Stat>
          <Stat icon={HardHat} label="BPJS Ketenagakerjaan" big accent="brand" value={rp(payroll.total_bpjs_tk)} hint="setoran periode ini" testId="stat-total-bpjs-tk">
            <Delta d={compare?.total_bpjs_tk} prev={prevName} testId="delta-total-bpjs-tk" />
          </Stat>
          <Stat icon={LockKeyhole} label="Slip Dikunci" big accent={payroll.slips && payroll.approved === payroll.slips ? "emerald" : "amber"} value={`${payroll.approved}/${payroll.slips}`} hint={payroll.slips && payroll.approved === payroll.slips ? "semua slip sudah di-approve" : "belum semua di-approve"} testId="stat-approved" />
        </div>
      )}
      {/* banner hanya tampil bila ada draft yang diajukan / ditolak; tanpa teks "tidak ada ..." (user 13 Okt 2026) */}
      {notes.length > 0 && (
        <div className="mb-6 space-y-2" data-testid="notifications-panel">
          {notes.map((n) => <Notice key={n.period_id} n={n} />)}
        </div>
      )}
      {period && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-6">
            <Stat wide icon={Users} label="Karyawan Periode Ini" accent="brand" value={counts.in_period} hint="punya slip di periode ini" testId="stat-employees">
              <Delta d={compare?.in_period} prev={prevName} orang testId="delta-employees" />
            </Stat>
            <Stat icon={UserPlus} label="Karyawan Baru" value={counts.new} accent="brand" dim={!counts.new} hint="mulai bekerja di periode ini" testId="stat-new" />
            <Stat icon={UserMinus} label="Karyawan Keluar" value={counts.left} accent="rose" dim={!counts.left} hint="tidak aktif di periode ini" testId="stat-left" />
            <Stat icon={UserX} label="Tidak Ikut Digaji" value={counts.unpaid} accent="amber" dim={!counts.unpaid} hint="unpaid / cuti di luar tanggungan" testId="stat-unpaid" />
            <Stat icon={AlertTriangle} label="Perlu Ditinjau" value={counts.data} accent={counts.data ? "amber" : "emerald"} hint="data belum lengkap: rekening, NPWP, dll" testId="stat-review" />
          </div>
          <Panel title={`Perlu Ditinjau · ${period.period_name}`} className="mb-6">
            {groups.map((g) => (
              <ReviewGroup key={g.key} g={g} pid={period.id} open={!!open[g.key]} onToggle={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))} />
            ))}
          </Panel>
        </>
      )}
      <Panel title="Periode Penggajian" right={<Link to="/hr-manager/payroll" className="tap text-xs font-semibold text-brand-700 hover:underline" data-testid="dashboard-all-periods-link">Kelola</Link>}>
        <div className="divide-y divide-slate-100">
          {periods.map((p) => (
            <Link key={p.id} to={`/hr-manager/payroll/${p.id}`} data-testid={`dashboard-period-${p.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 group">
              <div>
                <div className="font-semibold text-slate-800">{p.period_name}</div>
                <div className="text-xs text-slate-500">{formatDateRange(p.start_date, p.end_date)}</div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge map={PERIOD_STATUS} status={p.status} />
                <ArrowRight className="h-4 w-4 text-slate-400 group-hover:translate-x-1 transition-transform" />
              </div>
            </Link>
          ))}
          {!periods.length && <div className="px-5 py-6 text-sm text-slate-500">Belum ada periode.</div>}
        </div>
      </Panel>
    </div>
  );
}
