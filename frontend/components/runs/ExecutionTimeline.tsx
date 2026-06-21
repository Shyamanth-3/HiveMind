import { cn } from "@/lib/utils";
import { backendRoleToPersona, getPersonaIcon, getPersonaColor } from "@/lib/agentNames";
import type { Event, BackendRoleKey } from "@/types";

// =============================================================================
// ExecutionTimeline — Chronological events for a single run
// =============================================================================

interface ExecutionTimelineProps {
  events: Event[];
  className?: string;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ExecutionTimeline({ events, className }: ExecutionTimelineProps) {
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return (
    <div className={cn("space-y-0", className)}>
      {sorted.map((event, i) => {
        const agent = event.agent;
        const color = agent ? getPersonaColor(agent) : "var(--muted-foreground)";
        const Icon = agent ? getPersonaIcon(agent) : null;
        const persona = agent ? backendRoleToPersona[agent] : "System";
        const isLast = i === sorted.length - 1;
        const isRejected = event.event_type === "task_rejected";
        const isApproved = event.event_type === "task_approved";

        return (
          <div key={event.id} className="flex gap-3">
            {/* Timeline line */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "h-6 w-6 rounded-full flex items-center justify-center shrink-0 border",
                  isRejected && "border-[var(--hm-danger)] bg-[var(--hm-danger)]/10",
                  isApproved && "border-[var(--hm-success)] bg-[var(--hm-success)]/10",
                  !isRejected && !isApproved && "border-border bg-[var(--hm-surface-elevated)]"
                )}
              >
                {Icon && (
                  <Icon className="h-3 w-3" style={{ color }} />
                )}
                {!Icon && (
                  <span className="h-2 w-2 rounded-full bg-muted-foreground" />
                )}
              </div>
              {!isLast && (
                <div className="w-px flex-1 bg-border" />
              )}
            </div>

            {/* Content */}
            <div
              className={cn(
                "flex-1 pb-4 min-w-0",
                isRejected && "animate-hm-flash-danger",
                isApproved && "animate-hm-flash-success"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-semibold" style={{ color }}>
                    {persona}
                  </span>
                  <span className="text-xs font-mono text-muted-foreground">
                    {event.event_type}
                  </span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {event.cost_usd > 0 && (
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      ₹{(event.cost_usd * 83).toFixed(2)}
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {formatLatency(event.latency_ms)}
                  </span>
                  <span className="text-[10px] text-muted-foreground/60 tabular-nums">
                    {formatTime(event.created_at)}
                  </span>
                </div>
              </div>
              {isRejected && event.payload && (
                <p className="mt-1 text-[11px] text-[var(--hm-danger)]/80">
                  Reason: {(event.payload as { reason?: string }).reason || "Quality check failed"}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
