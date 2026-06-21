"use client";

import { cn } from "@/lib/utils";
import { Brain } from "lucide-react";

// =============================================================================
// MemorySearchBar — "Search by meaning, not just keywords"
// =============================================================================

interface MemorySearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch?: () => void;
  className?: string;
}

export function MemorySearchBar({
  value,
  onChange,
  onSearch,
  className,
}: MemorySearchBarProps) {
  return (
    <div className={cn("relative", className)}>
      <Brain className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[var(--hm-primary)]" />
      <input
        type="text"
        placeholder="Search by meaning, not just keywords..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSearch?.()}
        className={cn(
          "h-12 w-full rounded-xl border border-border bg-card pl-12 pr-4",
          "text-sm text-foreground placeholder:text-muted-foreground",
          "transition-all duration-300",
          "focus:border-[var(--hm-primary)]/50 focus:outline-none focus:ring-2 focus:ring-[var(--hm-primary)]/20",
          "focus:shadow-lg focus:shadow-[var(--hm-primary)]/5"
        )}
      />
      <div className="absolute right-3 top-1/2 -translate-y-1/2">
        <kbd className="hidden sm:inline-flex items-center gap-1 rounded-md border border-border bg-[var(--hm-surface-elevated)] px-1.5 py-0.5 text-[10px] text-muted-foreground">
          ⏎ Search
        </kbd>
      </div>
    </div>
  );
}
