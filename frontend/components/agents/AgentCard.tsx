"use client";

import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { backendRoleToPersona, getPersonaIcon, getPersonaColor, getPersonaDescription } from "@/lib/agentNames";
import type { AgentStatusData, BackendRoleKey } from "@/types";

// =============================================================================
// AgentCard — Detailed agent card for the Agents page
// =============================================================================

interface AgentCardProps {
  data: AgentStatusData;
  onClick?: () => void;
  isSelected?: boolean;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AgentCard({ data, onClick, isSelected }: AgentCardProps) {
  const Icon = getPersonaIcon(data.agent);
  const color = getPersonaColor(data.agent);
  const persona = backendRoleToPersona[data.agent];
  const description = getPersonaDescription(data.agent);

  return (
    <div
      onClick={onClick}
      className={cn(
        "rounded-xl border bg-card p-5 transition-all duration-300 cursor-pointer",
        "hover:shadow-lg hover:shadow-[var(--hm-primary)]/5",
        isSelected
          ? "border-[var(--hm-primary)]/50 shadow-md shadow-[var(--hm-primary)]/10"
          : "border-border hover:border-border/80",
        data.status === "working" && "animate-hm-glow"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className="rounded-xl p-2.5"
            style={{ backgroundColor: `${color}15` }}
          >
            <Icon className="h-5 w-5" style={{ color }} />
          </div>
          <div>
            <h3 className="text-base font-bold text-foreground">{persona}</h3>
            <p className="text-xs text-muted-foreground max-w-[200px] leading-relaxed">
              {description}
            </p>
          </div>
        </div>
        <StatusBadge status={data.status} />
      </div>

      {/* Current Task */}
      {data.current_task && (
        <div className="mb-4 rounded-lg bg-[var(--hm-primary)]/5 border border-[var(--hm-primary)]/10 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hm-primary)] mb-0.5">
            Current Task
          </p>
          <p className="text-xs text-foreground truncate">{data.current_task}</p>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-border/50">
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Last Active
          </p>
          <p className="text-xs font-medium text-foreground mt-0.5">
            {formatDate(data.last_activity)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Completed
          </p>
          <p className="text-xs font-medium text-foreground mt-0.5">
            {data.tasks_completed}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Success
          </p>
          <p className={cn(
            "text-xs font-medium mt-0.5",
            data.success_rate >= 80 ? "text-[var(--hm-success)]" : "text-[var(--hm-warning)]"
          )}>
            {data.success_rate}%
          </p>
        </div>
      </div>
    </div>
  );
}
