import { useEffect, useState } from "react";
import { DatabaseZap } from "lucide-react";
import { api } from "@/lib/api";

export const IntegrationBadge = ({ system }) => {
  const [mode, setMode] = useState(null);
  useEffect(() => { api.get("/hr/integrations").then((r) => setMode(r.data[system]?.mode)); }, [system]);
  if (!mode) return null;
  const mock = mode === "mock";
  return (
    <span data-testid={`integration-badge-${system}`} className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[11px] font-semibold uppercase tracking-wide ${mock ? "bg-amber-50 border-amber-300 text-amber-800" : "bg-emerald-50 border-emerald-300 text-emerald-700"}`}>
      <DatabaseZap className="h-3.5 w-3.5" /> {system === "rosy" ? "ROSY" : "RUMATKU"} · {mock ? "Data Simulasi" : "API Live"}
    </span>
  );
};
