import { Lightbulb, TrendingUp, Clock, IndianRupee } from "lucide-react";

// =============================================================================
// FindingCard — Callout card stating experimental findings
// =============================================================================

export function FindingCard() {
  return (
    <div className="rounded-xl border border-[var(--hm-primary)]/20 bg-gradient-to-br from-[var(--hm-primary)]/5 via-background to-background p-6">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-[var(--hm-primary)]/10 p-2 shrink-0">
          <Lightbulb className="h-5 w-5 text-[var(--hm-primary)]" />
        </div>
        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-bold text-foreground">
              Key Finding
            </h3>
            <p className="text-xs text-muted-foreground mt-1 italic">
              Illustrative data — these numbers are mocked to demonstrate the
              experiment tracking UI, not actual results.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-3.5 w-3.5 text-[var(--hm-success)]" />
              <p className="text-xs text-foreground">
                <span className="font-semibold text-[var(--hm-primary)]">
                  Reflection wins on quality:
                </span>{" "}
                91% vs 78% task success rate, 9% vs 22% retry rate.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <IndianRupee className="h-3.5 w-3.5 text-[var(--hm-warning)]" />
              <p className="text-xs text-foreground">
                <span className="font-semibold text-[var(--hm-warning)]">
                  ReAct wins on efficiency:
                </span>{" "}
                ₹1.85 vs ₹2.40 per task, 4.2s vs 6.8s latency.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-foreground">
                <span className="font-semibold">
                  Recommendation:
                </span>{" "}
                Use Reflection for quality-critical tasks (final deliverables),
                ReAct for speed-sensitive tasks (research gathering). The cost
                difference at free-tier scale is negligible.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
