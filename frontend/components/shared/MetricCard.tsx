import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import { Info } from "lucide-react";

// =============================================================================
// MetricCard — Redesigned SaaS card for key metrics
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
}: MetricCardProps) {
  // Sparkline mini bars (hardcoded varying heights for visual effect)
  const sparklineHeights = ["40%", "60%", "30%", "80%", "100%"];

  return (
    <div
      className={cn(
        "bg-[var(--hm-surface)] border border-border rounded-xl p-4 transition-all duration-200 hover:border-[var(--hm-primary)]/50",
        className
      )}
    >
      {/* Top: Metric title */}
      <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
        {label}
      </p>

      {/* Middle: Value and Sparkline */}
      <div className="mt-2 flex items-center justify-between">
        <p className="text-[24px] font-semibold text-white">
          {value}
        </p>
        
        {/* Sparkline */}
        <div className="flex items-end gap-[2px] h-[40px]">
          {sparklineHeights.map((h, i) => (
            <div
              key={i}
              className={cn(
                "w-[6px] rounded-sm bg-[var(--hm-primary)]",
                i < 2 ? "opacity-40" : "opacity-100"
              )}
              style={{ height: h }}
            />
          ))}
        </div>
      </div>

      {/* Bottom: Separator and info */}
      <div className="mt-4 border-t border-border pt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* We replace the user requested 'info icon' with their original passed icon, or just an info icon + trend text */}
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="text-[12px] text-muted-foreground">
            {trend?.label || "vs last period"}
          </span>
        </div>
        
        {trend && (
          <span
            className={cn(
              "text-[12px] font-medium flex items-center gap-1",
              trend.value >= 0
                ? "text-[var(--hm-success)]"
                : "text-[var(--hm-danger)]"
            )}
          >
            {trend.value >= 0 ? "↗" : "↘"} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
    </div>
  );
}
