"use client";

import { PageHeader } from "@/components/shared/PageHeader";
import { WorkflowYamlViewer } from "@/components/workflow/WorkflowYamlViewer";
import { WorkflowGraphView } from "@/components/workflow/WorkflowGraphView";
import { LiveRunSection } from "@/components/workflow/LiveRunSection";
import { Suspense } from "react";

// =============================================================================
// Workflow Page — Automation Engine
// =============================================================================

export default function WorkflowPage() {
  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Automation Engine"
        subtitle="Declarative workflow definitions — the orchestrator reads YAML, not hardcoded control flow."
      />

      {/* Live run telemetry over WebSocket (useSearchParams needs a Suspense boundary) */}
      <Suspense fallback={<p className="text-[12px] text-muted-foreground">Loading live view…</p>}>
        <LiveRunSection />
      </Suspense>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <WorkflowYamlViewer />
        <WorkflowGraphView />
      </div>
    </div>
  );
}
