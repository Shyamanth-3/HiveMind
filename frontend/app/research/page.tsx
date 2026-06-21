"use client";

import { PageHeader } from "@/components/shared/PageHeader";
import { ExperimentComparisonTable } from "@/components/research/ExperimentComparisonTable";
import { ReasoningDiagram } from "@/components/research/ReasoningDiagram";
import { FindingCard } from "@/components/research/FindingCard";
import { FlaskConical } from "lucide-react";

// =============================================================================
// Research Page — Reasoning Pattern Experiments
// =============================================================================

export default function ResearchPage() {
  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Reasoning Experiments"
        subtitle="Investigating how different reasoning patterns affect task quality, cost, and latency."
      />

      {/* Hypothesis */}
      <div className="hm-glass rounded-xl p-5">
        <div className="flex items-start gap-3">
          <FlaskConical className="h-5 w-5 text-[var(--hm-primary)] shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Hypothesis
            </h3>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              &ldquo;Reflection improves task success rate at the cost of higher latency
              and token spend, compared to plain ReAct.&rdquo;
            </p>
          </div>
        </div>
      </div>

      {/* Reasoning Diagrams */}
      <ReasoningDiagram />

      {/* Comparison Table */}
      <ExperimentComparisonTable />

      {/* Finding Card */}
      <FindingCard />
    </div>
  );
}
