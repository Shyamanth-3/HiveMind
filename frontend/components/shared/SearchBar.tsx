import { cn } from "@/lib/utils";
import { Search } from "lucide-react";

// =============================================================================
// SearchBar — Styled search input with icon and glass effect
// =============================================================================

interface SearchBarProps {
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
}

export function SearchBar({
  placeholder = "Search...",
  value,
  onChange,
  className,
}: SearchBarProps) {
  return (
    <div className={cn("relative", className)}>
      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className={cn(
          "h-9 w-full rounded-lg border border-border bg-[var(--hm-surface-elevated)] pl-9 pr-3",
          "text-sm text-foreground placeholder:text-muted-foreground",
          "transition-all duration-200",
          "focus:border-[var(--hm-primary)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--hm-primary)]/30"
        )}
      />
    </div>
  );
}
