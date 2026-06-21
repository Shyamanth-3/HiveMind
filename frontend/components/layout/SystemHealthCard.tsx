import { cn } from "@/lib/utils";
import type { SystemService } from "@/types";
import { Database, Radio, Cpu } from "lucide-react";

// =============================================================================
// SystemHealthCard — Compact service status for sidebar
// =============================================================================

interface SystemHealthCardProps {
  service: SystemService;
  className?: string;
}

const serviceIcons: Record<string, typeof Database> = {
  PostgreSQL: Database,
  Redis: Radio,
  "LLM Provider": Cpu,
};

const statusDotClass: Record<string, string> = {
  online: "bg-[var(--hm-success)]",
  offline: "bg-muted-foreground",
  "cold-start": "bg-[var(--hm-warning)] animate-hm-cold-pulse",
  degraded: "bg-[var(--hm-warning)]",
};

export function SystemHealthCard({ service, className }: SystemHealthCardProps) {
  const Icon = serviceIcons[service.name] || Cpu;
  const dotClass = statusDotClass[service.status] || statusDotClass.offline;

  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 transition-colors",
        "hover:bg-[var(--hm-surface-elevated)]",
        className
      )}
    >
      <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-foreground truncate">
          {service.name}
        </p>
      </div>
      <span className={cn("h-2 w-2 rounded-full shrink-0", dotClass)} />
      {service.latency_ms !== undefined && (
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {service.latency_ms}ms
        </span>
      )}
    </div>
  );
}
