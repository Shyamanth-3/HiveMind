"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEventStream } from "@/hooks/useEventStream";
import type { TelemetryEvent } from "@/lib/telemetry/types";
import { describeEvent } from "@/lib/telemetry/view";
import { AgentPipeline } from "./AgentPipeline";
import { ConnectionBadge } from "./ConnectionBadge";
import { RevisionTimeline } from "./RevisionTimeline";

// =============================================================================
// LiveRunPanel — real-time view of ONE run, driven by the WebSocket telemetry stream.
// Kafka/PostgreSQL are the source of truth; this is a live view that recovers from them.
// =============================================================================

const EVENT_COLOR: Record<string, string> = {
  "run.completed": "var(--hm-success)",
  "run.failed": "var(--hm-danger)",
  "revision.requested": "var(--hm-warning)",
};

export function EventLog({ events, limit }: { events: TelemetryEvent[]; limit?: number }) {
  const shown = [...events].reverse().slice(0, limit ?? events.length);
  if (shown.length === 0) {
    return <p className="text-[12px] text-muted-foreground py-4 text-center">Waiting for events...</p>;
  }
  return (
    <div className="space-y-1" data-testid="event-log">
      {shown.map((e) => (
        <div
          key={e.event_id}
          data-testid="event-row"
          data-event-type={e.event_type}
          className="flex items-center gap-3 rounded-lg px-3 py-2 border-l-2 bg-[var(--hm-surface-elevated)]/30 animate-hm-slide-in"
          style={{ borderLeftColor: EVENT_COLOR[e.event_type] ?? "var(--hm-primary)" }}
        >
          <div className="flex-1 min-w-0">
            <span className="text-[12px] text-white">{describeEvent(e)}</span>{" "}
            <span className="text-[11px] text-gray-500 font-mono">{e.event_type}</span>
          </div>
          <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
            {new Date(e.timestamp).toLocaleTimeString()}
          </span>
        </div>
      ))}
    </div>
  );
}

export function LiveRunPanel({ runId }: { runId: string }) {
  const { events, state, connectionState, error, nextRetryMs, reconnect, isTerminal } = useEventStream({ runId });
  const goal = events.find((e) => e.event_type === "run.created")?.payload.goal;
  const failure = state?.failure;

  return (
    <div className="bg-[var(--hm-surface)] border border-border rounded-xl p-5 space-y-5" data-testid="live-run-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14px] font-semibold text-white">Live workflow</h3>
          <p className="text-[11px] text-muted-foreground font-mono truncate">{runId}</p>
          {typeof goal === "string" && <p className="text-[12px] text-gray-300 mt-1 line-clamp-2">{goal}</p>}
        </div>
        <ConnectionBadge
          state={connectionState}
          detail={
            connectionState === "reconnecting" && nextRetryMs !== null
              ? `retry in ${Math.ceil(nextRetryMs / 1000)}s`
              : error
          }
          onReconnect={reconnect}
        />
      </div>

      {state?.status === "completed" && (
        <div
          data-testid="terminal-completed"
          className="flex items-center gap-2 rounded-lg border border-[var(--hm-success)]/40 bg-[var(--hm-success)]/10 px-3 py-2 text-[12px] text-[var(--hm-success)]"
        >
          <CheckCircle2 className="h-4 w-4" />
          Run completed
          {state.revision.count > 0 && ` after ${state.revision.count} revision${state.revision.count === 1 ? "" : "s"}`}
        </div>
      )}
      {state?.status === "failed" && (
        <div
          data-testid="terminal-failed"
          className="rounded-lg border border-[var(--hm-danger)]/40 bg-[var(--hm-danger)]/10 px-3 py-2 text-[12px] text-[var(--hm-danger)]"
        >
          <div className="flex items-center gap-2 font-medium">
            <XCircle className="h-4 w-4" />
            Run failed{failure?.failed_stage ? ` at ${failure.failed_stage}` : ""}
            {failure?.error_type ? ` — ${failure.error_type}` : ""}
          </div>
          {failure?.message && <p className="mt-1 text-[11px] opacity-90 break-words">{failure.message}</p>}
        </div>
      )}
      {!isTerminal && connectionState !== "connected" && connectionState !== "connecting" && (
        <p className="text-[11px] text-muted-foreground" data-testid="paused-note">
          Live updates are paused. The run keeps going on the server; this view catches up when the connection returns.
        </p>
      )}

      <AgentPipeline state={state} />
      <RevisionTimeline events={events} maxRevisions={state?.revision.max} />

      <div>
        <h4 className="text-[12px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">Events</h4>
        <div className={cn("max-h-[360px] overflow-y-auto hm-scrollbar pr-1")}>
          <EventLog events={events} />
        </div>
      </div>
    </div>
  );
}
