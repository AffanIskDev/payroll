import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { formatDate } from "@/lib/format";

// Peringatan sebelum "Fetch Data Terbaru" selagi periode berjalan (user 12 Okt 2026): absensi hari ini belum selesai,
// jadi karyawan yang belum absen masuk saat sinkron terhitung 1 hari alfa sampai periodenya disinkron ulang.
export default function SyncTodayDialog({ day, periodName, onConfirm, onCancel }) {
  return (
    <AlertDialog open={!!day} onOpenChange={(o) => !o && onCancel()}>
      <AlertDialogContent data-testid="sync-today-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Absensi hari ini belum selesai</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                Periode {periodName} masih berjalan, jadi absensi hari ini ({formatDate(day)}) ikut diambil. Karyawan yang
                <b> belum absen masuk saat sinkron</b> akan terhitung <b>1 hari alfa</b> — memotong gaji pokok, tunjangan
                jabatan, dan tunjangan kehadiran.
              </p>
              <p>Angka itu baru benar setelah disinkron ulang sesudah hari kerja selesai (paling aman besok pagi). Sinkron ulang dulu sebelum mengajukan atau Lock &amp; Approve.</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="sync-today-cancel">Batal</AlertDialogCancel>
          <AlertDialogAction data-testid="sync-today-confirm" onClick={onConfirm}>Tetap Sinkron</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
