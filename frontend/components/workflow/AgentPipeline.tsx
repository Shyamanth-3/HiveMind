"use client";

import { CheckCircle2, Circle, Loader2, RotateCcw, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { AGENT_IDS, type AgentState, type AgentStatus, type WorkflowState } from "@/lib/telemetry/types";
import { AGENT_LABELS, AGENT_ROLE, STATUS_LABELS } from "@/lib/telemetry/view";

// =============================================================================
// AgentPipeline — Queen → Architect → Scout → Builder → Guardian, driven only by backend state.
// =============================================================================

const STYLE: Record<AgentStatus, { text: string; border: string; icon: React.ReactNode }> = {
  pending: { text: "text-muted-foreground", border: "border-border", icon: <Circle className="h-4 w-4" /> },
  running: {
    text: "text-[var(--hm-primary)]",
    border: "border-[var(--hm-primary)]",
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
  },
  completed: {
    text: "text-[var(--hm-success)]",
    border: "border-[var(--hm-success)]/50",
    icon: <CheckCircle2 className="h-4 w-4" />,
  },
  failed: {
    text: "text-[var(--hm-danger)]",
    border: "border-[var(--hm-danger)]/60",
    icon: <XCircle className="h-4 w-4" />,
  },
  revision: {
    text: "text-[var(--hm-warning)]",
    border: "border-[var(--hm-warning)]/60",
    icon: <RotateCcw className="h-4 w-4" />,
  },
};

function AgentCard({ id, agent }: { id: string; agent: AgentState }) {
  const s = STYLE[agent.status];
  return (
    <div
      data-testid={`agent-${id}`}
      data-status={agent.status}
      className={cn("flex-1 min-w-[120px] rounded-lg border bg-[var(--hm-surface-elevated)]/40 px-3 py-2", s.border)}
    >
      <div className={cn("flex items-center gap-2", s.text)}>
        {s.icon}
        <span className="text-[13px] font-semibold text-white">{AGENT_LABELS[id as keyof typeof AGENT_LABELS]}</span>
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground">
        {AGENT_ROLE[id as keyof typeof AGENT_ROLE]}
        {agent.revision > 0 && <span className="ml-1 text-[var(--hm-warning)]">· rev {agent.revision}</span>}
      </div>
      <div className={cn("text-[11px] font-medium", s.text)}>
        {agent.status === "failed" && agent.error_type ? `Failed (${agent.error_type})` : STATUS_LABELS[agent.status]}
      </div>
    </div>
  );
}

export function AgentPipeline({ state }: { state: WorkflowState | null }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2" data-testid="agent-pipeline">
      {AGENT_IDS.map((id, i) => (
        <div key={id} className="flex flex-1 items-center gap-2 min-w-[140px]">
          <AgentCard id={id} agent={state?.agents[id] ?? { status: "pending", revision: 0 }} />
          {i < AGENT_IDS.length - 1 && <span className="text-muted-foreground hidden md:block">→</span>}
        </div>
      ))}
    </div>
  );
}
