import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { mockAgentStatus } from "@/lib/mockData";
import { backendRoleToPersona, getPersonaIcon, getPersonaColor, getPersonaDescription } from "@/lib/agentNames";
import type { BackendRoleKey } from "@/types";

// =============================================================================
// AgentHealthGrid — 5 compact agent cards for dashboard overview
// =============================================================================

export function AgentHealthGrid() {
  return (
    <div className="hm-glass rounded-xl p-5">
      <h3 className="text-sm font-semibold text-foreground mb-4">
        Agent Health
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {mockAgentStatus.map((agent) => {
          const Icon = getPersonaIcon(agent.agent);
          const color = getPersonaColor(agent.agent);
          const persona = backendRoleToPersona[agent.agent];

          return (
            <div
              key={agent.agent}
              className={cn(
                "rounded-lg border border-border/50 bg-background/50 p-3.5 transition-all duration-300",
                "hover:border-border hover:bg-[var(--hm-surface-elevated)]",
                agent.status === "working" && "animate-hm-glow"
              )}
            >
              <div className="flex items-center gap-2.5 mb-2.5">
                <div
                  className="rounded-lg p-1.5"
                  style={{ backgroundColor: `${color}15` }}
                >
                  <Icon
                    className="h-4 w-4"
                    style={{ color }}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground truncate">
                    {persona}
                  </p>
                </div>
              </div>
              <StatusBadge status={agent.status} size="sm" />
              {agent.current_task && (
                <p className="mt-2 text-[11px] text-muted-foreground truncate">
                  {agent.current_task}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
