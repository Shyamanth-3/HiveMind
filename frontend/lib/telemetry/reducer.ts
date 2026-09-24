// =============================================================================
// HiveMind — telemetry state reducer (pure, framework-free)
//
// Frontend state is a cache derived from the server: the snapshot establishes it, events extend it,
// `workflow.state` messages carry the authoritative run/agent state. Deduplication is by event_id,
// so a replayed / re-delivered event can never be applied twice.
// =============================================================================

import type { ServerMessage, TelemetryEvent, WorkflowState } from "./types";

export interface StreamState {
  events: TelemetryEvent[];
  ids: Record<string, true>;
  state: WorkflowState | null;
  /** id of the last event applied, sent as ?last_event_id= when reconnecting */
  lastEventId: string | null;
  /** true once a snapshot has been applied */
  synced: boolean;
}

export type StreamAction =
  | { type: "message"; message: ServerMessage }
  | { type: "reset" };

export const initialStreamState: StreamState = {
  events: [],
  ids: {},
  state: null,
  lastEventId: null,
  synced: false,
};

const ts = (e: TelemetryEvent): number => {
  const t = Date.parse(e.timestamp);
  return Number.isNaN(t) ? 0 : t;
};

/**
 * Add events not seen before. Server order is (created_at, id): an event that arrives late (out of order) is
 * inserted after the last event that is not newer than it, so the timeline stays chronological; ties keep
 * arrival order. `lastEventId` is always the newest event, i.e. a correct resume cursor.
 */
function append(base: StreamState, incoming: TelemetryEvent[]): StreamState {
  const events = [...base.events];
  const ids = { ...base.ids };
  let added = false;
  for (const ev of incoming) {
    if (ids[ev.event_id]) continue; // already applied
    ids[ev.event_id] = true;
    added = true;
    let i = events.length;
    while (i > 0 && ts(events[i - 1]) > ts(ev)) i--;
    events.splice(i, 0, ev);
  }
  if (!added) return base;
  return { ...base, events, ids, lastEventId: events[events.length - 1].event_id };
}

export function reduce(s: StreamState, action: StreamAction): StreamState {
  if (action.type === "reset") return initialStreamState;
  const m = action.message;
  switch (m.type) {
    case "workflow.snapshot": {
      // full: the server is authoritative for the whole history -> start from scratch.
      // resume: keep what we have, add what we missed.
      const base = m.mode === "full" ? initialStreamState : s;
      const next = append(base, m.events);
      return { ...next, state: m.state, synced: true };
    }
    case "workflow.event":
      return append(s, [m]);
    case "workflow.state":
      return s.state && s.state.run_id !== m.run_id ? s : { ...s, state: m.state };
    default:
      return s; // heartbeat / pong
  }
}

/** The workflow (not the socket) reached a terminal state. */
export function isTerminal(s: StreamState): boolean {
  if (s.state && s.state.status !== "running") return true;
  const last = s.events[s.events.length - 1];
  return last?.event_type === "run.completed" || last?.event_type === "run.failed";
}
