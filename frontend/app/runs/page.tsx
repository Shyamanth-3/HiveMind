"use client";

import { PageHeader } from "@/components/shared/PageHeader";
import { RunTable } from "@/components/runs/RunTable";

// =============================================================================
// Runs Page — Workflow Execution Monitoring
// =============================================================================

export default function RunsPage() {
  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Workflow Execution"
        subtitle="Monitor autonomous agent runs — click any row to inspect the task graph, timeline, and retry cycles."
      />
      <RunTable />
    </div>
  );
}