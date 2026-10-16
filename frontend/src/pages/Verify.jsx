import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldCheck, Clock, ShieldX, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import logoRpi from "@/assets/logo-rpi.png";
import logoRumat from "@/assets/logo-rumat.png";

// Halaman publik tanpa login: dibuka dari QR di slip gaji (user 14 Okt 2026, backend verify.py). Isinya jawaban
// GET /api/verify/{kode} yang dibaca dari database saat halaman dibuka — tanpa nominal gaji, nama karyawan disamarkan.
// 15 Okt 2026 (masukan user agar terlihat resmi): kop sama dengan slip, "Dokumen Terverifikasi", nomor dokumen & tanggal
// terbit yang juga tercetak di slip, status penerbitan & persetujuan, dan waktu pemeriksaan.
const TONE = {
  emerald: "bg-emerald-50 border-emerald-200 text-emerald-800",
  amber: "bg-amber-50 border-amber-200 text-amber-900",
  rose: "bg-rose-50 border-rose-200 text-rose-800",
  slate: "bg-slate-100 border-slate-200 text-slate-700",
};
const DOT = { emerald: "bg-emerald-500", amber: "bg-amber-500" };

const VIEW = {
  sah: { icon: ShieldCheck, tone: "emerald", title: "Dokumen Terverifikasi",
    text: (d) => `Slip gaji ini tercatat di sistem payroll ${d.perusahaan || "perusahaan"}, sudah diterbitkan dan disetujui HRD.` },
  belum_disetujui: { icon: Clock, tone: "amber", title: "Dokumen Belum Terbit",
    text: () => "Slip ini masih draft dan belum disetujui HRD, jadi belum berlaku sebagai slip gaji resmi. Jangan dijadikan acuan." },
  tidak_ditemukan: { icon: ShieldX, tone: "rose", title: "Dokumen Tidak Terverifikasi",
    text: () => "Kode pada QR tidak terdaftar di sistem payroll, jadi keaslian slip ini tidak dapat dipastikan. Hubungi HRD perusahaan yang menerbitkannya." },
  gagal: { icon: WifiOff, tone: "slate", title: "Verifikasi belum bisa dilakukan",
    text: () => "Layanan verifikasi tidak dapat dihubungi. Coba lagi beberapa saat lagi." },
};

// status_penerbitan & status_persetujuan dari backend
const STATUS = {
  diterbitkan: { tone: "emerald", label: "Diterbitkan" },
  belum_diterbitkan: { tone: "amber", label: "Belum diterbitkan" },
  disetujui: { tone: "emerald", label: "Disetujui" },
  menunggu: { tone: "amber", label: "Menunggu persetujuan HRD" },
};

// "15 Oktober 2026 pukul 11.48 WIB"; di layar sempit patah sebelum "pukul", bukan sebelum "WIB"
const wib = (iso) => {
  if (!iso) return "-";
  const at = new Date(iso);
  const date = at.toLocaleDateString("id-ID", { timeZone: "Asia/Jakarta", day: "numeric", month: "long", year: "numeric" });
  const time = at.toLocaleTimeString("id-ID", { timeZone: "Asia/Jakarta", hour: "2-digit", minute: "2-digit" });
  return `${date} pukul\u00a0${time}\u00a0WIB`;
};

// "SG/RUMAT/2026/09/0001": di layar sempit patah setelah kode perusahaan, tidak di tengah angka
const DocNumber = ({ value }) => {
  const [kind, company, ...rest] = value.split("/");
  return rest.length ? <>{kind}/{company}/<wbr />{rest.join("/")}</> : value;
};

const Section = ({ title, children }) => (
  <div>
    <div className="px-4 sm:px-5 pt-4 pb-1 text-xs font-semibold text-slate-500">{title}</div>
    <dl className="divide-y divide-slate-100">{children}</dl>
  </div>
);

const Row = ({ k, children, testId }) => (
  <div className="flex items-start justify-between gap-4 px-4 sm:px-5 py-3 text-sm">
    <dt className="text-slate-500 shrink-0">{k}</dt>
    <dd className="text-right font-medium text-slate-900 break-words min-w-0" data-testid={testId}>{children || "-"}</dd>
  </div>
);

const Status = ({ value, note }) => {
  const s = STATUS[value];
  if (!s) return null;
  return (
    <span className="inline-flex flex-col items-end">
      <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${DOT[s.tone]}`} />{s.label}</span>
      {note && <span className="text-xs font-normal text-slate-500 mt-0.5">{note}</span>}
    </span>
  );
};

export default function Verify() {
  const { code } = useParams();
  const [res, setRes] = useState({ loading: true });

  useEffect(() => {
    const before = document.title;
    document.title = "Verifikasi Dokumen | RUSA";
    return () => { document.title = before; };
  }, []);

  useEffect(() => {
    let live = true;
    setRes({ loading: true });
    api.get(`/verify/${encodeURIComponent(code)}`)
      .then((r) => live && setRes({ data: r.data, key: r.data.status, at: r.data.diperiksa_pada }))
      .catch((e) => live && setRes(e?.response?.status === 404
        ? { key: "tidak_ditemukan", at: new Date().toISOString() } : { key: "gagal" }));
    return () => { live = false; };
  }, [code]);

  const v = VIEW[res.key];
  const d = res.data;
  const signer = [d?.penandatangan?.nama, d?.penandatangan?.jabatan].filter(Boolean).join(", ");
  return (
    <div className="min-h-screen bg-background px-3 py-4 sm:px-4 sm:py-10" data-testid="verify-page">
      <div className="mx-auto w-full max-w-lg">
        {/* satu lembar putih seperti kertas slip (user 15 Okt 2026: kop & judul jangan menggantung di latar abu-abu) */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-4 py-5 sm:px-8 sm:py-7" data-testid="verify-sheet">
          {/* kop sama dengan slip PDF: RPI kiri, RUMAT kanan */}
          <div className="flex items-center justify-between pb-4 mb-5 border-b border-slate-200" data-testid="verify-kop">
            <img src={logoRpi} alt="RPI" className="h-10 w-auto" />
            <img src={logoRumat} alt="RUMAT" className="h-8 w-auto" />
          </div>
          <div className="text-center mb-5">
            <div className="text-sm font-semibold text-brand-700">Verifikasi Dokumen</div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">Slip Gaji Karyawan</h1>
          </div>
          {res.loading ? <div className="text-center text-sm text-slate-500" data-testid="verify-loading">Memeriksa slip...</div> : (
            <>
              <div className={`flex gap-3 rounded-lg border px-4 sm:px-5 py-4 ${TONE[v.tone]}`} data-testid="verify-status" data-status={res.key}>
                <v.icon className="h-6 w-6 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold" data-testid="verify-status-title">{v.title}</div>
                  <div className="text-sm mt-0.5">{v.text(d || {})}</div>
                </div>
              </div>
              {d && (
                <div className="mt-4 border border-slate-200 rounded-lg divide-y divide-slate-100 pb-1" data-testid="verify-details">
                  {res.key === "sah" && (
                    <Section title="Detail dokumen">
                      {d.id_dokumen && <Row k="ID Dokumen" testId="verify-id-dokumen"><span className="num"><DocNumber value={d.id_dokumen} /></span></Row>}
                      <Row k="Tanggal terbit" testId="verify-tanggal-terbit">{wib(d.diterbitkan_pada)}</Row>
                      <Row k="Perusahaan" testId="verify-perusahaan">{d.perusahaan}</Row>
                      <Row k="Periode" testId="verify-periode">{d.periode}</Row>
                      <Row k="Nama karyawan" testId="verify-karyawan">{d.karyawan}</Row>
                    </Section>
                  )}
                  <Section title="Status">
                    <Row k="Penerbitan" testId="verify-status-penerbitan"><Status value={d.status_penerbitan} /></Row>
                    <Row k="Persetujuan" testId="verify-status-persetujuan">
                      <Status value={d.status_persetujuan} note={d.status_persetujuan === "disetujui" ? `oleh ${signer || "HRD"}` : ""} />
                    </Row>
                  </Section>
                </div>
              )}
              {res.at && (
                <div className="mt-3 space-y-0.5 text-xs text-slate-500" data-testid="verify-meta">
                  <div>Kode verifikasi: <span className="num text-slate-700">{d?.kode || code}</span></div>
                  <div>Diperiksa langsung ke sistem payroll: {wib(res.at)}</div>
                </div>
              )}
              {res.key === "sah" && (
                <p className="mt-4 text-xs text-slate-500" data-testid="verify-note">
                  Cocokkan ID dokumen, tanggal terbit, nama karyawan, dan periode di atas dengan yang tertera pada slip. Bila ada yang
                  berbeda, slip tersebut bukan dokumen asli — hubungi HRD. Nominal gaji tidak ditampilkan di halaman ini.
                </p>
              )}
            </>
          )}
        </div>
        <div className="mt-5 px-4 text-center text-xs text-slate-500">
          Layanan verifikasi dokumen RUSA — RUMAT Salary Administration
        </div>
      </div>
    </div>
  );
}
