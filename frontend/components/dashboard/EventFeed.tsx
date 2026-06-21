"use client";

import { cn } from "@/lib/utils";
import { useEventStream } from "@/hooks/useEventStream";
import { backendRoleToPersona, getPersonaIcon, getPersonaColor } from "@/lib/agentNames";
import type { BackendRoleKey, Event } from "@/types";

// =============================================================================
// EventFeed — Live scrolling event feed simulating WebSocket stream
// =============================================================================

function getFlashClass(eventType: string): string {
  if (eventType === "task_approved") return "animate-hm-flash-success";
  if (eventType === "task_rejected") return "animate-hm-flash-danger";
  return "";
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function EventRow({ event }: { event: Event }) {
  const agent = event.agent;
  const Icon = agent ? getPersonaIcon(agent) : null;
  const color = agent ? getPersonaColor(agent) : "var(--muted-foreground)";
  const persona = agent ? backendRoleToPersona[agent] : "System";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 animate-hm-slide-in",
        "border-l-2 transition-all",
        getFlashClass(event.event_type)
      )}
      style={{ borderLeftColor: color }}
    >
      {Icon && <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />}
      {!Icon && (
        <span className="h-3.5 w-3.5 rounded-full bg-muted-foreground/30 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <span className="text-xs font-medium" style={{ color }}>
          [{persona}]
        </span>{" "}
        <span className="text-xs text-muted-foreground font-mono">
          {event.event_type}
        </span>
      </div>
      <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
        {formatLatency(event.latency_ms)}
      </span>
    </div>
  );
}

export function EventFeed() {
  const { events, isConnected } = useEventStream(15);

  return (
    <div className="hm-glass rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-foreground">
          Live Event Stream
        </h3>
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              isConnected
                ? "bg-[var(--hm-success)] animate-hm-pulse"
                : "bg-[var(--hm-danger)]"
            )}
          />
          <span className="text-[10px] text-muted-foreground">
            {isConnected ? "Live" : "Connecting..."}
          </span>
        </div>
      </div>
      <div className="space-y-1 max-h-[380px] overflow-y-auto hm-scrollbar">
        {events.length === 0 && (
          <p className="text-xs text-muted-foreground py-4 text-center">
            Waiting for events...
          </p>
        )}
        {events.map((event) => (
          <EventRow key={event.id} event={event} />
        ))}
      </div>
    </div>
  );
}
