"use client";

import { cn } from "@/lib/utils";
import type { ConnectionState } from "@/lib/telemetry/types";

// =============================================================================
// ConnectionBadge — WebSocket transport state. Says nothing about the workflow:
// a dropped connection is "Reconnecting", never "Failed".
// =============================================================================

const CONFIG: Record<ConnectionState, { label: string; dot: string; pulse: boolean }> = {
  connecting: { label: "Connecting…", dot: "bg-[var(--hm-warning)]", pulse: true },
  connected: { label: "Live", dot: "bg-[var(--hm-success)]", pulse: true },
  reconnecting: { label: "Reconnecting…", dot: "bg-[var(--hm-warning)]", pulse: true },
  disconnected: { label: "Disconnected", dot: "bg-[var(--muted-foreground)]", pulse: false },
  error: { label: "Connection error", dot: "bg-[var(--hm-danger)]", pulse: false },
};

export function ConnectionBadge({
  state,
  detail,
  onReconnect,
}: {
  state: ConnectionState;
  detail?: string | null;
  onReconnect?: () => void;
}) {
  const c = CONFIG[state];
  return (
    <div className="flex items-center gap-2" data-testid="connection-badge" data-state={state}>
      <div className="flex items-center gap-1.5 bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-2 py-1">
        <span className={cn("h-1.5 w-1.5 rounded-full", c.dot, c.pulse && "animate-hm-pulse")} />
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{c.label}</span>
      </div>
      {detail && state !== "connected" && (
        <span className="text-[10px] text-muted-foreground truncate max-w-[220px]" title={detail}>
          {detail}
        </span>
      )}
      {(state === "error" || state === "disconnected") && onReconnect && (
        <button
          type="button"
          onClick={onReconnect}
          className="text-[10px] uppercase tracking-widest text-[var(--hm-primary)] hover:underline"
        >
          Reconnect
        </button>
      )}
    </div>
  );
}
