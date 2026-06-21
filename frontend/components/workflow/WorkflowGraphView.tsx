"use client";

import { TaskGraphView } from "@/components/runs/TaskGraphView";
import { Plus } from "lucide-react";

// =============================================================================
// WorkflowGraphView — Template mode of TaskGraphView + disabled Add button
// =============================================================================

export function WorkflowGraphView() {
  return (
    <div className="hm-glass rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-foreground">
          Workflow Graph — goal_to_deliverable
        </h3>
      </div>

      <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] p-4">
        <TaskGraphView mode="template" />
      </div>

      {/* Disabled Add Workflow button */}
      <div className="mt-4 flex justify-end">
        <div className="relative group">
          <button
            disabled
            className="flex items-center gap-2 rounded-lg border border-border bg-[var(--hm-surface-elevated)] px-4 py-2 text-xs font-medium text-muted-foreground cursor-not-allowed opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Workflow
          </button>
          {/* Tooltip */}
          <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-10">
            <div className="rounded-lg border border-border bg-[var(--hm-surface-elevated)] px-3 py-2 shadow-lg max-w-xs">
              <p className="text-xs text-muted-foreground">
                Visual builder coming in a future version — v1 ships one hand-edited template by design.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
