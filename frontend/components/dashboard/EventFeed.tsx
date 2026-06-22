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
  const agent = event.event_type === "system_alert" ? undefined : event.agent;
  const Icon = agent ? getPersonaIcon(agent) : null;
  const color = agent ? getPersonaColor(agent) : "var(--hm-primary)";
  const persona = agent ? backendRoleToPersona[agent] : "System";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 animate-hm-slide-in",
        "border-l-2 transition-all bg-[var(--hm-surface-elevated)]/30 hover:bg-[var(--hm-surface-elevated)]/80 mb-1",
        getFlashClass(event.event_type)
      )}
      style={{ borderLeftColor: color }}
    >
      {Icon && <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />}
      {!Icon && (
        <span className="h-3.5 w-3.5 rounded-full bg-[var(--hm-primary)]/30 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <span className="text-[12px] font-medium" style={{ color }}>
          [{persona}]
        </span>{" "}
        <span className="text-[12px] text-gray-400 font-mono tracking-tight">
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
    <div className="bg-[var(--hm-surface)] border border-border rounded-xl p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[14px] font-semibold text-white">
          Live Event Stream
        </h3>
        <div className="flex items-center gap-1.5 bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-2 py-1">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              isConnected
                ? "bg-[var(--hm-success)] animate-hm-pulse"
                : "bg-[var(--hm-danger)]"
            )}
          />
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            {isConnected ? "Live" : "Connecting..."}
          </span>
        </div>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto hm-scrollbar pr-2 min-h-[250px]">
        {events.length === 0 && (
          <p className="text-[12px] text-muted-foreground py-4 text-center">
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
