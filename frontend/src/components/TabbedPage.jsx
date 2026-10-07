import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const TabbedPage = ({ tabs }) => {
  const [params, setParams] = useSearchParams();
  const active = params.get("tab") || tabs[0][0];
  return (
    <Tabs value={active} onValueChange={(v) => setParams({ tab: v })}>
      <TabsList className="mb-5 bg-slate-200/60">
        {tabs.map(([k, label]) => (
          <TabsTrigger key={k} value={k} data-testid={`tab-${k}`} className="data-[state=active]:bg-white data-[state=active]:text-blue-900 font-semibold">{label}</TabsTrigger>
        ))}
      </TabsList>
      {tabs.map(([k, , Comp]) => <TabsContent key={k} value={k}><Comp /></TabsContent>)}
    </Tabs>
  );
};
