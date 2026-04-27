import { Input } from "./ui/input";

export function DateRangeFilter({
  start,
  end,
  onChange,
}: {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Input
        type="date"
        value={start}
        onChange={(e) => onChange(e.target.value, end)}
        className="w-auto"
      />
      <span className="text-muted-foreground">→</span>
      <Input
        type="date"
        value={end}
        onChange={(e) => onChange(start, e.target.value)}
        className="w-auto"
      />
    </div>
  );
}
