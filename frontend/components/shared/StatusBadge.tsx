import { cn } from "@/lib/utils";
import type { StatusValue } from "@/types";

// =============================================================================
// StatusBadge — Universal status indicator
// Uses the HiveMind status color mapping consistently across all surfaces.
// =============================================================================

interface StatusBadgeProps {
  status: StatusValue;
  className?: string;
  showDot?: boolean;
  size?: "sm" | "md";
}

const statusConfig: Record<
  StatusValue,
  { label: string; dotClass: string; bgClass: string; textClass: string }
> = {
  online: {
    label: "Online",
    dotClass: "bg-[var(--hm-success)]",
    bgClass: "bg-[var(--hm-success)]/10",
    textClass: "text-[var(--hm-success)]",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-[var(--hm-success)]",
    bgClass: "bg-[var(--hm-success)]/10",
    textClass: "text-[var(--hm-success)]",
  },
  approved: {
    label: "Approved",
    dotClass: "bg-[var(--hm-success)]",
    bgClass: "bg-[var(--hm-success)]/10",
    textClass: "text-[var(--hm-success)]",
  },
  idle: {
    label: "Idle",
    dotClass: "bg-[var(--muted-foreground)]",
    bgClass: "bg-[var(--muted-foreground)]/10",
    textClass: "text-[var(--muted-foreground)]",
  },
  pending: {
    label: "Pending",
    dotClass: "bg-[var(--muted-foreground)]",
    bgClass: "bg-[var(--muted-foreground)]/10",
    textClass: "text-[var(--muted-foreground)]",
  },
  offline: {
    label: "Offline",
    dotClass: "bg-[var(--muted-foreground)]",
    bgClass: "bg-[var(--muted-foreground)]/10",
    textClass: "text-[var(--muted-foreground)]",
  },
  working: {
    label: "Working",
    dotClass: "bg-[var(--hm-primary)] animate-hm-pulse",
    bgClass: "bg-[var(--hm-primary)]/10",
    textClass: "text-[var(--hm-primary)]",
  },
  running: {
    label: "Running",
    dotClass: "bg-[var(--hm-primary)] animate-hm-pulse",
    bgClass: "bg-[var(--hm-primary)]/10",
    textClass: "text-[var(--hm-primary)]",
  },
  rejected: {
    label: "Rejected",
    dotClass: "bg-[var(--hm-danger)]",
    bgClass: "bg-[var(--hm-danger)]/10",
    textClass: "text-[var(--hm-danger)]",
  },
  failed: {
    label: "Failed",
    dotClass: "bg-[var(--hm-danger)]",
    bgClass: "bg-[var(--hm-danger)]/10",
    textClass: "text-[var(--hm-danger)]",
  },
  "cold-start": {
    label: "Cold Start",
    dotClass: "bg-[var(--hm-warning)] animate-hm-cold-pulse",
    bgClass: "bg-[var(--hm-warning)]/10",
    textClass: "text-[var(--hm-warning)]",
  },
  degraded: {
    label: "Degraded",
    dotClass: "bg-[var(--hm-warning)]",
    bgClass: "bg-[var(--hm-warning)]/10",
    textClass: "text-[var(--hm-warning)]",
  },
};

export function StatusBadge({
  status,
  className,
  showDot = true,
  size = "md",
}: StatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-bold uppercase tracking-wider border",
        size === "sm" ? "px-2 py-[2px] text-[10px]" : "px-2.5 py-1 text-[10px]",
        config.bgClass,
        config.textClass,
        // dynamically generate border color based on textClass
        config.textClass.replace('text-', 'border-').concat('/20'),
        className
      )}
    >
      {showDot && (
        <span
          className={cn(
            "rounded-full shrink-0",
            size === "sm" ? "h-[6px] w-[6px]" : "h-2 w-2",
            config.dotClass
          )}
        />
      )}
      {config.label}
    </span>
  );
}
