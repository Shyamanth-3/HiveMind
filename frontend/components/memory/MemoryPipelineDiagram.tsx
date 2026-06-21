import { ArrowRight, Database, Brain, Search, FileText } from "lucide-react";

// =============================================================================
// MemoryPipelineDiagram — Write Path / Read Path diagram
// =============================================================================

export function MemoryPipelineDiagram() {
  return (
    <div className="hm-glass rounded-xl p-5 space-y-6">
      <h3 className="text-sm font-semibold text-foreground">
        Memory Pipeline
      </h3>

      {/* Write Path */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--hm-success)] mb-3">
          Write Path
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { icon: FileText, label: "Agent Output" },
            { icon: null, label: "→" },
            { icon: FileText, label: "Chunk" },
            { icon: null, label: "→" },
            { icon: Brain, label: "Embed" },
            { icon: null, label: "→" },
            { icon: Database, label: "pgvector" },
          ].map((step, i) =>
            step.icon ? (
              <div
                key={i}
                className="flex items-center gap-1.5 rounded-lg border border-border bg-[var(--hm-surface-elevated)] px-3 py-2"
              >
                <step.icon className="h-3.5 w-3.5 text-[var(--hm-success)]" />
                <span className="text-xs text-foreground">{step.label}</span>
              </div>
            ) : (
              <ArrowRight
                key={i}
                className="h-3.5 w-3.5 text-muted-foreground shrink-0"
              />
            )
          )}
        </div>
      </div>

      {/* Read Path */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--hm-primary)] mb-3">
          Read Path
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { icon: FileText, label: "New Task" },
            { icon: null, label: "→" },
            { icon: Brain, label: "Embed Query" },
            { icon: null, label: "→" },
            { icon: Search, label: "Similarity Search" },
            { icon: null, label: "→" },
            { icon: Database, label: "Top-k Chunks" },
            { icon: null, label: "→" },
            { icon: FileText, label: "Inject into Prompt" },
          ].map((step, i) =>
            step.icon ? (
              <div
                key={i}
                className="flex items-center gap-1.5 rounded-lg border border-border bg-[var(--hm-surface-elevated)] px-3 py-2"
              >
                <step.icon className="h-3.5 w-3.5 text-[var(--hm-primary)]" />
                <span className="text-xs text-foreground">{step.label}</span>
              </div>
            ) : (
              <ArrowRight
                key={i}
                className="h-3.5 w-3.5 text-muted-foreground shrink-0"
              />
            )
          )}
        </div>
      </div>

      {/* Callout */}
      <div className="rounded-lg border border-[var(--hm-primary)]/20 bg-[var(--hm-primary)]/5 px-4 py-3">
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Note:</span> Running
          on <span className="text-[var(--hm-primary)] font-medium">pgvector</span> inside
          the primary Postgres instance — no separate vector database in v1.
        </p>
      </div>
    </div>
  );
}
