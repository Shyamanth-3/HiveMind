// =============================================================================
// HiveMind — pure view helpers for telemetry (labels, revision timeline). No React.
// =============================================================================

import type { AgentId, AgentStatus, TelemetryEvent } from "./types";

export const AGENT_LABELS: Record<AgentId, string> = {
  queen: "Queen",
  architect: "Architect",
  scout: "Scout",
  builder: "Builder",
  guardian: "Guardian",
};

export const AGENT_ROLE: Record<AgentId, string> = {
  queen: "Strategy",
  architect: "Architecture",
  scout: "Research",
  builder: "Task graph",
  guardian: "Review",
};

export const STATUS_LABELS: Record<AgentStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  revision: "Needs revision",
};

const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);
const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);

/** One-line, human description of an event (uses only the backend's sanitised summary). */
export function describeEvent(e: TelemetryEvent): string {
  const p = e.payload;
  switch (e.event_type) {
    case "run.created":
      return "Run started";
    case "strategy.created":
      return `Queen produced a strategy${num(p.phases) !== undefined ? ` (${p.phases} phases)` : ""}`;
    case "architecture.created":
      return `Architect designed ${num(p.components) ?? "the"} components`;
    case "research.completed":
      return `Scout finished research${num(p.findings) !== undefined ? ` (${p.findings} findings)` : ""}`;
    case "tasks.generated": {
      const rev = num(p.revision_number) ?? e.revision_number ?? 0;
      const n = num(p.task_count);
      return rev > 0
        ? `Builder produced revision ${rev}${n !== undefined ? ` (${n} tasks)` : ""}`
        : `Builder produced ${n ?? ""} tasks`.replace("  ", " ");
    }
    case "review.completed": {
      const verdict = str(p.verdict);
      const rev = num(p.revision_number) ?? e.revision_number ?? 0;
      const what = rev > 0 ? `revision ${rev}` : "the plan";
      return verdict === "approved"
        ? `Guardian approved ${what}`
        : verdict === "needs_revision"
          ? `Guardian: ${what} needs revision`
          : `Guardian ${verdict ?? "reviewed"} ${what}`;
    }
    case "revision.requested":
      return `Revision ${num(p.revision_number) ?? ""} requested`.replace("  ", " ");
    case "run.completed":
      return "Run completed";
    case "run.failed":
      return `Run failed${str(p.error_type) ? ` (${p.error_type})` : ""}`;
    default:
      return e.event_type;
  }
}

export type RevisionOutcome = "pending" | "approved" | "needs_revision" | "rejected";

export interface RevisionStep {
  revision: number;
  reason: string;
  feedback: string[];
  changeCount: number;
  requestedAt: string;
  /** tasks in the Builder output for this revision, once produced */
  taskCount?: number;
  /** Guardian's verdict on this revision's output, once reviewed */
  outcome: RevisionOutcome;
}

export interface RevisionTimeline {
  /** Guardian's verdict on the ORIGINAL output (null until reviewed) */
  originalVerdict: string | null;
  revisions: RevisionStep[];
}

/** Build the Guardian -> revision -> Builder -> Guardian narrative from events (no timers, no guessing). */
export function buildRevisionTimeline(events: TelemetryEvent[]): RevisionTimeline {
  const steps = new Map<number, RevisionStep>();
  let originalVerdict: string | null = null;

  for (const e of events) {
    const p = e.payload;
    const rev = num(p.revision_number) ?? e.revision_number ?? 0;
    if (e.event_type === "revision.requested") {
      const n = num(p.revision_number) ?? rev;
      steps.set(n, {
        revision: n,
        reason: str(p.reason) ?? "",
        feedback: Array.isArray(p.feedback) ? (p.feedback as unknown[]).filter((f): f is string => typeof f === "string") : [],
        changeCount: num(p.requested_changes) ?? 0,
        requestedAt: e.timestamp,
        outcome: "pending",
      });
    } else if (e.event_type === "tasks.generated" && rev > 0) {
      const s = steps.get(rev);
      if (s) s.taskCount = num(p.task_count);
    } else if (e.event_type === "review.completed") {
      const verdict = str(p.verdict) ?? null;
      if (rev === 0) originalVerdict = verdict;
      else {
        const s = steps.get(rev);
        if (s && (verdict === "approved" || verdict === "needs_revision" || verdict === "rejected")) s.outcome = verdict;
      }
    }
  }
  return { originalVerdict, revisions: [...steps.values()].sort((a, b) => a.revision - b.revision) };
}
