import { TabbedPage } from "@/components/TabbedPage";
import TaxYtd from "@/pages/hr/TaxYtd";
import TaxForms from "@/pages/hr/TaxForms";
import Schedules from "@/pages/hr/Schedules";
import Rotations from "@/pages/hr/Rotations";
import ShiftRecap from "@/pages/hr/ShiftRecap";
import OvertimeRecap from "@/pages/hr/OvertimeRecap";

export const TaxPage = () => <TabbedPage tabs={[["ytd", "Saldo Awal YTD", TaxYtd], ["a1", "Bukti Potong 1721-A1", TaxForms]]} />;
export const ScheduleShiftPage = () => <TabbedPage tabs={[["schedules", "Jadwal Kerja", Schedules], ["rotations", "Rotasi Shift", Rotations]]} />;
export const RecapPage = () => <TabbedPage tabs={[["shift", "Rekap Shift", ShiftRecap], ["overtime", "Rekap Lembur", OvertimeRecap]]} />;
