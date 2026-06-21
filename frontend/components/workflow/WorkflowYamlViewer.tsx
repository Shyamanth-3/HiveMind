"use client";

import { cn } from "@/lib/utils";
import { FileCode } from "lucide-react";

// =============================================================================
// WorkflowYamlViewer — Read-only syntax-highlighted YAML viewer
// Node IDs use backend role keys in the raw YAML.
// =============================================================================

const workflowYaml = `# goal_to_deliverable — HiveMind v1 Workflow Template
# This is the single workflow template shipped with v1.
# Workflows are declarative YAML the orchestrator reads,
# not hardcoded control flow.

name: goal_to_deliverable
version: "1.0"
trigger: webhook

nodes:
  ceo_plan:
    agent: ceo_agent
    type: plan
    on: trigger
    outputs:
      - plan_text
      - success_criteria

  pm_breakdown:
    agent: pm_agent
    type: breakdown
    when: ceo_plan.completed
    inputs:
      - ceo_plan.plan_text
      - ceo_plan.success_criteria
    outputs:
      - task_graph

  research_gather:
    agent: research_agent
    type: research
    when: pm_breakdown.completed
    inputs:
      - pm_breakdown.task_graph
    outputs:
      - memory_chunks
    parallel_with: dev_build

  dev_build:
    agent: developer_agent
    type: build
    when: pm_breakdown.completed
    inputs:
      - pm_breakdown.task_graph
      - research_gather.memory_chunks  # RAG context
    outputs:
      - deliverable
    parallel_with: research_gather

  qa_review:
    agent: reviewer_qa_agent
    type: review
    when:
      all:
        - research_gather.completed
        - dev_build.completed
    inputs:
      - dev_build.deliverable
      - ceo_plan.success_criteria
    outputs:
      - verdict  # task_approved | task_rejected

  # Reject loop — re-queues dev_build with feedback
  reject_loop:
    on: qa_review.rejected
    target: dev_build
    max_retries: 3
    feedback: qa_review.feedback

  store_notify:
    type: finalize
    when: qa_review.approved
    actions:
      - store_deliverable
      - notify_operator`;

// Simple syntax highlighting for YAML
function highlightYaml(yaml: string): React.ReactNode[] {
  return yaml.split("\n").map((line, i) => {
    let highlighted: React.ReactNode;

    if (line.trimStart().startsWith("#")) {
      // Comment
      highlighted = <span className="text-muted-foreground/60">{line}</span>;
    } else if (line.includes(":") && !line.trimStart().startsWith("-")) {
      // Key-value
      const colonIdx = line.indexOf(":");
      const key = line.substring(0, colonIdx);
      const value = line.substring(colonIdx);
      highlighted = (
        <>
          <span className="text-[var(--hm-primary)]">{key}</span>
          <span className="text-muted-foreground">{value}</span>
        </>
      );
    } else if (line.trimStart().startsWith("-")) {
      // List item
      const indent = line.match(/^(\s*)/)?.[1] || "";
      const rest = line.trimStart().substring(1);
      highlighted = (
        <>
          <span className="text-muted-foreground">{indent}-</span>
          <span className="text-[var(--hm-success)]">{rest}</span>
        </>
      );
    } else {
      highlighted = <span className="text-foreground">{line}</span>;
    }

    return (
      <div key={i} className="flex">
        <span className="inline-block w-8 shrink-0 text-right pr-3 text-muted-foreground/40 select-none text-[11px]">
          {i + 1}
        </span>
        <span className="flex-1">{highlighted}</span>
      </div>
    );
  });
}

export function WorkflowYamlViewer() {
  return (
    <div className="hm-glass rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border px-5 py-3">
        <FileCode className="h-4 w-4 text-[var(--hm-primary)]" />
        <span className="text-sm font-semibold text-foreground">
          goal_to_deliverable.yaml
        </span>
        <span className="text-[10px] text-muted-foreground">— read-only</span>
      </div>
      <div className="p-4 overflow-x-auto hm-scrollbar">
        <pre className="font-mono text-xs leading-5">
          {highlightYaml(workflowYaml)}
        </pre>
      </div>
    </div>
  );
}
