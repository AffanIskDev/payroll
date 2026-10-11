import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { TabbedPage } from "@/components/TabbedPage";
import TaxYtd from "@/pages/hr/TaxYtd";
import TaxForms from "@/pages/hr/TaxForms";
import ShiftRecap from "@/pages/hr/ShiftRecap";
import OvertimeRecap from "@/pages/hr/OvertimeRecap";

const TAX_TABS = [["ytd", "Saldo Awal YTD", TaxYtd], ["a1", "Bukti Potong 1721-A1", TaxForms]];

// Saldo awal YTD diisi sekali; kalau tahun ini sudah ada (diimpor / pernah diisi), halaman langsung membuka Bukti
// Potong (permintaan user 10 Okt 2026). Tab yang dipilih sendiri (?tab=) tetap dihormati.
export const TaxPage = () => {
  const [params] = useSearchParams();
  const chosen = params.get("tab");
  const [hasBalances, setHasBalances] = useState(null);
  useEffect(() => {
    if (chosen) return;
    api.get("/hr/tax-balances", { params: { year: new Date().getFullYear() } })
      .then((r) => setHasBalances(r.data.length > 0)).catch(() => setHasBalances(false));
  }, [chosen]);
  if (!chosen && hasBalances === null) return <div className="text-sm text-slate-500">Memuat...</div>;
  return <TabbedPage tabs={TAX_TABS} defaultTab={hasBalances ? "a1" : "ytd"} />;
};
export const RecapPage = () => <TabbedPage tabs={[["shift", "Rekap Shift", ShiftRecap], ["overtime", "Rekap Lembur", OvertimeRecap]]} />;
