"use client";

import { cn } from "@/lib/utils";
import { X, ArrowRight } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  backendRoleToPersona,
  getPersonaIcon,
  getPersonaColor,
  getPersonaDescription,
  getAgentContract,
} from "@/lib/agentNames";
import { mockEvents } from "@/lib/mockData";
import type { AgentStatusData, BackendRoleKey } from "@/types";

// =============================================================================
// AgentDetailPanel — Expanded view with INPUT→OUTPUT contract + activity log
// =============================================================================

interface AgentDetailPanelProps {
  data: AgentStatusData | null;
  onClose: () => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function AgentDetailPanel({ data, onClose }: AgentDetailPanelProps) {
  if (!data) return null;

  const Icon = getPersonaIcon(data.agent);
  const color = getPersonaColor(data.agent);
  const persona = backendRoleToPersona[data.agent];
  const description = getPersonaDescription(data.agent);
  const contract = getAgentContract(data.agent);

  // Activity log scoped to this agent
  const agentEvents = mockEvents
    .filter((e) => e.agent === data.agent)
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    .slice(0, 10);

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <div
            className="rounded-xl p-2.5"
            style={{ backgroundColor: `${color}15` }}
          >
            <Icon className="h-5 w-5" style={{ color }} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-foreground">{persona}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-[var(--hm-surface-elevated)] hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-5 space-y-5">
        {/* Status */}
        <div className="flex items-center gap-3">
          <StatusBadge status={data.status} />
          {data.current_task && (
            <span className="text-xs text-muted-foreground">
              → {data.current_task}
            </span>
          )}
        </div>

        {/* INPUT → OUTPUT Contract */}
        <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Agent Contract
          </h4>
          <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-start">
            {/* Inputs */}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hm-primary)] mb-2">
                Input
              </p>
              <ul className="space-y-1.5">
                {contract.inputs.map((input, i) => (
                  <li key={i} className="text-xs text-foreground flex items-start gap-1.5">
                    <span className="text-muted-foreground shrink-0 mt-0.5">•</span>
                    {input}
                  </li>
                ))}
              </ul>
            </div>

            {/* Arrow */}
            <div className="flex items-center justify-center pt-6">
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>

            {/* Outputs */}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hm-success)] mb-2">
                Output
              </p>
              <ul className="space-y-1.5">
                {contract.outputs.map((output, i) => (
                  <li key={i} className="text-xs text-foreground flex items-start gap-1.5">
                    <span className="text-muted-foreground shrink-0 mt-0.5">•</span>
                    {output}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Publishes */}
          <div className="mt-3 pt-3 border-t border-border/50">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Publishes
            </p>
            <div className="flex gap-2 flex-wrap">
              {contract.publishes.map((evt) => (
                <span
                  key={evt}
                  className="rounded-md bg-[var(--hm-primary)]/10 px-2 py-0.5 text-[10px] font-mono text-[var(--hm-primary)]"
                >
                  {evt}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Recent Activity
          </h4>
          <div className="space-y-2">
            {agentEvents.length === 0 && (
              <p className="text-xs text-muted-foreground">No recent activity</p>
            )}
            {agentEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between rounded-lg bg-[var(--hm-surface-elevated)] px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-muted-foreground">
                    {event.event_type}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {event.run_id}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {event.cost_usd > 0 && (
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      ₹{(event.cost_usd * 83).toFixed(2)}
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {event.latency_ms}ms
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
