import { TabbedPage } from "@/components/TabbedPage";
import TaxYtd from "@/pages/hr/TaxYtd";
import TaxForms from "@/pages/hr/TaxForms";
import ShiftRecap from "@/pages/hr/ShiftRecap";
import OvertimeRecap from "@/pages/hr/OvertimeRecap";

export const TaxPage = () => <TabbedPage tabs={[["ytd", "Saldo Awal YTD", TaxYtd], ["a1", "Bukti Potong 1721-A1", TaxForms]]} />;
export const RecapPage = () => <TabbedPage tabs={[["shift", "Rekap Shift", ShiftRecap], ["overtime", "Rekap Lembur", OvertimeRecap]]} />;
