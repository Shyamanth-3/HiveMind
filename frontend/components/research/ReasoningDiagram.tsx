import { ArrowRight, RotateCcw } from "lucide-react";

// =============================================================================
// ReasoningDiagram — ReAct vs Reflection loop diagrams
// Framed as the Builder's internal loop being experimented on.
// =============================================================================

export function ReasoningDiagram() {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      {/* ReAct Loop */}
      <div className="hm-glass rounded-xl p-5">
        <h4 className="text-sm font-semibold text-foreground mb-1">
          ReAct Pattern
        </h4>
        <p className="text-[10px] text-muted-foreground mb-4">
          Builder&apos;s baseline loop — act immediately, iterate on observations
        </p>
        <div className="flex flex-col items-center gap-0">
          {["Thought", "Action", "Observation"].map((step, i) => (
            <div key={step} className="flex flex-col items-center">
              <div className="rounded-lg border border-[var(--hm-warning)]/30 bg-[var(--hm-warning)]/5 px-5 py-2.5 text-center">
                <span className="text-xs font-medium text-[var(--hm-warning)]">
                  {step}
                </span>
              </div>
              {i < 2 && (
                <div className="h-4 w-px bg-[var(--hm-warning)]/30 my-1" />
              )}
            </div>
          ))}
          <div className="flex items-center gap-2 mt-2">
            <RotateCcw className="h-3 w-3 text-[var(--hm-warning)]/50" />
            <span className="text-[10px] text-muted-foreground">
              repeat until done
            </span>
          </div>
        </div>
      </div>

      {/* Reflection Loop */}
      <div className="hm-glass rounded-xl p-5">
        <h4 className="text-sm font-semibold text-foreground mb-1">
          Reflection Pattern
        </h4>
        <p className="text-[10px] text-muted-foreground mb-4">
          Builder&apos;s experimental loop — self-critique against Queen&apos;s criteria
        </p>
        <div className="flex flex-col items-center gap-0">
          {["Draft", "Self-Critique vs. Criteria", "Revise"].map((step, i) => (
            <div key={step} className="flex flex-col items-center">
              <div className="rounded-lg border border-[var(--hm-primary)]/30 bg-[var(--hm-primary)]/5 px-5 py-2.5 text-center">
                <span className="text-xs font-medium text-[var(--hm-primary)]">
                  {step}
                </span>
              </div>
              {i < 2 && (
                <div className="h-4 w-px bg-[var(--hm-primary)]/30 my-1" />
              )}
            </div>
          ))}
          <div className="flex items-center gap-2 mt-2">
            <RotateCcw className="h-3 w-3 text-[var(--hm-primary)]/50" />
            <span className="text-[10px] text-muted-foreground">
              repeat until criteria met
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
