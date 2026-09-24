"use client";

import Link from "next/link";
import { useApi } from "@/hooks/useApi";
import { useEventStream } from "@/hooks/useEventStream";
import { fetchRuns } from "@/lib/api";
import { ConnectionBadge } from "@/components/workflow/ConnectionBadge";
import { EventLog } from "@/components/workflow/LiveRunPanel";

// =============================================================================
// EventFeed — live event stream of the most recent run, over a real WebSocket.
// (Replaces the former simulated replay of historical events.)
// =============================================================================

export function EventFeed() {
  const { data: runs } = useApi(() => fetchRuns(), []);
  const latest = runs?.[0] ?? null;
  const { events, state, connectionState, error, reconnect } = useEventStream({ runId: latest?.id });

  return (
    <div className="bg-[var(--hm-surface)] border border-border rounded-xl p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4 gap-2">
        <div className="min-w-0">
          <h3 className="text-[14px] font-semibold text-white">Live Event Stream</h3>
          {latest && (
            <p className="text-[10px] text-muted-foreground truncate">
              {state?.status ?? latest.status} · {latest.goal.slice(0, 48)}
            </p>
          )}
        </div>
        <ConnectionBadge
          state={latest ? connectionState : "disconnected"}
          detail={error}
          onReconnect={reconnect}
        />
      </div>
      <div className="flex-1 overflow-y-auto hm-scrollbar pr-2 min-h-[250px]" data-testid="dashboard-event-feed">
        {latest ? (
          <EventLog events={events} limit={15} />
        ) : (
          <p className="text-[12px] text-muted-foreground py-4 text-center">No runs yet.</p>
        )}
      </div>
      {latest && (
        <Link
          href={`/workflow?run=${latest.id}`}
          className="mt-3 text-[11px] uppercase tracking-widest text-[var(--hm-primary)] hover:underline"
        >
          Open live workflow →
        </Link>
      )}
    </div>
  );
}
