import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const TabbedPage = ({ tabs, defaultTab }) => {
  const [params, setParams] = useSearchParams();
  const active = params.get("tab") || defaultTab || tabs[0][0];
  return (
    <Tabs value={active} onValueChange={(v) => setParams({ tab: v })}>
      {/* di HP tab setinggi ±36px supaya mudah disentuh; mulai sm kembali ke ukuran bawaan */}
      <TabsList className="mb-5 bg-slate-200/60 h-auto sm:h-9">
        {tabs.map(([k, label]) => (
          <TabsTrigger key={k} value={k} data-testid={`tab-${k}`} className="data-[state=active]:bg-white data-[state=active]:text-blue-900 font-semibold py-2 sm:py-1.5">{label}</TabsTrigger>
        ))}
      </TabsList>
      {tabs.map(([k, , Comp]) => <TabsContent key={k} value={k}><Comp /></TabsContent>)}
    </Tabs>
  );
};
