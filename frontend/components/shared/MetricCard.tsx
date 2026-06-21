import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

// =============================================================================
// MetricCard — Glassmorphic card for key metrics
// =============================================================================

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: { value: number; label: string };
  className?: string;
  iconColor?: string;
}

export function MetricCard({
  label,
  value,
  icon: Icon,
  trend,
  className,
  iconColor = "text-[var(--hm-primary)]",
}: MetricCardProps) {
  return (
    <div
      className={cn(
        "hm-glass rounded-xl p-5 transition-all duration-300",
        "hover:border-[var(--hm-primary)]/20 hover:shadow-lg hover:shadow-[var(--hm-primary)]/5",
        "group cursor-default",
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className="text-2xl font-bold tracking-tight text-foreground">
            {value}
          </p>
          {trend && (
            <p
              className={cn(
                "text-xs font-medium",
                trend.value >= 0
                  ? "text-[var(--hm-success)]"
                  : "text-[var(--hm-danger)]"
              )}
            >
              {trend.value >= 0 ? "↑" : "↓"} {Math.abs(trend.value)}%{" "}
              <span className="text-muted-foreground">{trend.label}</span>
            </p>
          )}
        </div>
        <div
          className={cn(
            "rounded-lg p-2.5 transition-colors duration-300",
            "bg-[var(--hm-primary)]/10 group-hover:bg-[var(--hm-primary)]/20"
          )}
        >
          <Icon className={cn("h-5 w-5", iconColor)} />
        </div>
      </div>
    </div>
  );
}
