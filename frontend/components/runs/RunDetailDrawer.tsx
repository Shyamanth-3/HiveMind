"use client";

import { cn } from "@/lib/utils";
import { X, AlertTriangle, CheckCircle, RotateCcw } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { TaskGraphView } from "./TaskGraphView";
import { ExecutionTimeline } from "./ExecutionTimeline";
import type { Run } from "@/types";
import { getTasksForRun, getEventsForRun } from "@/lib/mockData";

// =============================================================================
// RunDetailDrawer — Slide-in drawer showing run details
// =============================================================================

interface RunDetailDrawerProps {
  run: Run | null;
  isOpen: boolean;
  onClose: () => void;
}

export function RunDetailDrawer({ run, isOpen, onClose }: RunDetailDrawerProps) {
  if (!run) return null;

  const tasks = getTasksForRun(run.id);
  const events = getEventsForRun(run.id);
  const hasRetry = tasks.some((t) => t.retry_count > 0);

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-background border-l border-border",
          "transform transition-transform duration-300 ease-in-out",
          "overflow-y-auto hm-scrollbar",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/95 backdrop-blur-sm px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-muted-foreground">
              {run.id}
            </span>
            <StatusBadge status={run.status} size="sm" />
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-[var(--hm-surface-elevated)] hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {/* Goal */}
          <div>
            <h2 className="text-lg font-bold text-foreground mb-2">
              {run.goal}
            </h2>
          </div>

          {/* Queen's Plan */}
          <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Queen&apos;s Plan
            </h3>
            <p className="text-sm text-foreground whitespace-pre-line leading-relaxed">
              {run.plan_text}
            </p>
          </div>

          {/* Success Criteria */}
          <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Success Criteria
            </h3>
            <ul className="space-y-2">
              {run.success_criteria.map((criterion, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                  <CheckCircle className="h-4 w-4 text-[var(--hm-success)] shrink-0 mt-0.5" />
                  <span>{criterion}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Retry Indicator */}
          {hasRetry && (
            <div className="flex items-center gap-3 rounded-lg border border-[var(--hm-danger)]/30 bg-[var(--hm-danger)]/5 p-4">
              <RotateCcw className="h-5 w-5 text-[var(--hm-danger)] shrink-0" />
              <div>
                <p className="text-sm font-semibold text-[var(--hm-danger)]">
                  Reject → Retry Cycle Detected
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Guardian rejected the initial output. Builder revised and resubmitted successfully.
                  This is autonomous self-correction in action.
                </p>
              </div>
            </div>
          )}

          {/* Task Graph */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Task Graph
            </h3>
            <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
              <TaskGraphView tasks={tasks} mode="live" />
            </div>
          </div>

          {/* Execution Timeline */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
              Execution Timeline
            </h3>
            <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
              <ExecutionTimeline events={events} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
