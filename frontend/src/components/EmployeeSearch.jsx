import { useState } from "react";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

export const EmployeeSearch = ({ employees, value, onChange }) => {
  const [open, setOpen] = useState(false);
  const cur = employees.find((e) => e.id === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button data-testid="attendance-employee-search" className="w-72 flex items-center justify-between gap-2 border border-slate-300 rounded-md px-3 py-1.5 text-sm bg-white hover:border-slate-400">
          <span className="flex items-center gap-2 truncate"><Search className="h-4 w-4 text-slate-400 shrink-0" />{cur ? `${cur.nik} · ${cur.name}` : <span className="text-slate-400">Ketik nama atau NIK</span>}</span>
          <ChevronsUpDown className="h-4 w-4 text-slate-400 shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <Command filter={(v, s) => (v.toLowerCase().includes(s.toLowerCase()) ? 1 : 0)}>
          <CommandInput data-testid="attendance-employee-search-input" placeholder="Ketik nama atau NIK..." />
          <CommandList>
            <CommandEmpty>Karyawan tidak ditemukan.</CommandEmpty>
            {employees.map((e) => (
              <CommandItem key={e.id} value={`${e.nik} ${e.name} ${e.department || ""}`} data-testid={`employee-option-${e.nik}`} onSelect={() => { onChange(e.id); setOpen(false); }}>
                <Check className={`h-4 w-4 mr-2 ${e.id === value ? "opacity-100" : "opacity-0"}`} />
                <div>
                  <div className="text-sm font-medium">{e.name}</div>
                  <div className="text-xs text-slate-500 num">{e.nik} · {e.department}</div>
                </div>
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};
