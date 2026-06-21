"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { RunDetailDrawer } from "./RunDetailDrawer";
import { mockRuns } from "@/lib/mockData";
import type { Run, RunStatus } from "@/types";

// =============================================================================
// RunTable — Full runs table with filters and drawer
// =============================================================================

function formatDuration(ms?: number): string {
  if (!ms) return "—";
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const statusFilters: { label: string; value: RunStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
];

export function RunTable() {
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<RunStatus | "all">("all");

  const filteredRuns =
    statusFilter === "all"
      ? mockRuns
      : mockRuns.filter((r) => r.status === statusFilter);

  const openDrawer = (run: Run) => {
    setSelectedRun(run);
    setIsDrawerOpen(true);
  };

  return (
    <>
      {/* Filters */}
      <div className="flex items-center gap-2 mb-4">
        {statusFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setStatusFilter(filter.value)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              statusFilter === filter.value
                ? "bg-[var(--hm-primary)]/10 text-[var(--hm-primary)]"
                : "text-muted-foreground hover:bg-[var(--hm-surface-elevated)] hover:text-foreground"
            )}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="hm-glass rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background/30">
                <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Run ID
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Goal
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Created
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Duration
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => openDrawer(run)}
                  className="border-b border-border/50 transition-colors hover:bg-[var(--hm-surface-elevated)]/50 cursor-pointer"
                >
                  <td className="px-5 py-4 font-mono text-xs text-muted-foreground">
                    {run.id}
                  </td>
                  <td className="px-5 py-4 text-foreground max-w-[400px] truncate">
                    {run.goal}
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge status={run.status} size="sm" />
                  </td>
                  <td className="px-5 py-4 text-muted-foreground tabular-nums">
                    {formatDate(run.created_at)}
                  </td>
                  <td className="px-5 py-4 text-muted-foreground tabular-nums">
                    {formatDuration(run.duration_ms)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <RunDetailDrawer
        run={selectedRun}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </>
  );
}
