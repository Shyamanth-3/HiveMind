"use client";

import { cn } from "@/lib/utils";
import type { TelemetryEvent } from "@/lib/telemetry/types";
import { buildRevisionTimeline, type RevisionOutcome } from "@/lib/telemetry/view";

// =============================================================================
// RevisionTimeline — Guardian → needs revision → Revision N → Builder → Guardian → approved
// Only backend events are used; feedback text is the backend's sanitised summary (no prompts).
// =============================================================================

const OUTCOME: Record<RevisionOutcome, { label: string; cls: string }> = {
  pending: { label: "In progress", cls: "text-[var(--hm-primary)]" },
  approved: { label: "Guardian approved", cls: "text-[var(--hm-success)]" },
  needs_revision: { label: "Guardian: needs revision", cls: "text-[var(--hm-warning)]" },
  rejected: { label: "Guardian rejected", cls: "text-[var(--hm-danger)]" },
};

export function RevisionTimeline({ events, maxRevisions }: { events: TelemetryEvent[]; maxRevisions?: number }) {
  const { originalVerdict, revisions } = buildRevisionTimeline(events);
  if (revisions.length === 0 && originalVerdict !== "needs_revision") return null;

  return (
    <div className="space-y-2" data-testid="revision-timeline">
      <h4 className="text-[12px] font-semibold uppercase tracking-widest text-muted-foreground">Revisions</h4>
      <ol className="space-y-2 border-l border-border pl-4">
        <li className="text-[12px]" data-testid="revision-original">
          <span className="font-medium text-white">Guardian reviewed the original plan</span>{" "}
          <span className={originalVerdict === "approved" ? "text-[var(--hm-success)]" : "text-[var(--hm-warning)]"}>
            — {originalVerdict === "needs_revision" ? "needs revision" : (originalVerdict ?? "reviewing…")}
          </span>
        </li>
        {revisions.map((r) => {
          const o = OUTCOME[r.outcome];
          return (
            <li key={r.revision} className="text-[12px] space-y-0.5" data-testid={`revision-${r.revision}`} data-outcome={r.outcome}>
              <div>
                <span className="font-medium text-white">
                  Revision {r.revision}
                  {maxRevisions ? ` of ${maxRevisions}` : ""} requested
                </span>{" "}
                <span className="text-muted-foreground">
                  · {r.feedback.length} feedback · {r.changeCount} requested change{r.changeCount === 1 ? "" : "s"}
                </span>
              </div>
              {r.feedback.slice(0, 3).map((f, i) => (
                <div key={i} className="text-[11px] text-muted-foreground pl-3 line-clamp-2">
                  • {f}
                </div>
              ))}
              <div className="text-[11px] text-muted-foreground">
                Builder {r.taskCount !== undefined ? `produced ${r.taskCount} tasks` : "revising…"}
              </div>
              <div className={cn("text-[11px] font-medium", o.cls)}>{o.label}</div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
