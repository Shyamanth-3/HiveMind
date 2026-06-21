import { cn } from "@/lib/utils";

// =============================================================================
// ExperimentComparisonTable — ReAct vs Reflection comparison
// =============================================================================

interface MetricRow {
  metric: string;
  react: string;
  reflection: string;
  winner: "react" | "reflection" | "tie";
}

const comparisonData: MetricRow[] = [
  {
    metric: "Task Success Rate",
    react: "78%",
    reflection: "91%",
    winner: "reflection",
  },
  {
    metric: "Cost per Task",
    react: "₹1.85",
    reflection: "₹2.40",
    winner: "react",
  },
  {
    metric: "Avg Latency",
    react: "4.2s",
    reflection: "6.8s",
    winner: "react",
  },
  {
    metric: "Retry Rate",
    react: "22%",
    reflection: "9%",
    winner: "reflection",
  },
];

export function ExperimentComparisonTable() {
  return (
    <div className="hm-glass rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground">
          ReAct vs. Reflection — Experimental Results
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Mock data — clearly illustrative, not production metrics.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background/30">
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Metric
              </th>
              <th className="px-5 py-3 text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
                ReAct
              </th>
              <th className="px-5 py-3 text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Reflection
              </th>
              <th className="px-5 py-3 text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Winner
              </th>
            </tr>
          </thead>
          <tbody>
            {comparisonData.map((row) => (
              <tr
                key={row.metric}
                className="border-b border-border/50"
              >
                <td className="px-5 py-3 font-medium text-foreground">
                  {row.metric}
                </td>
                <td
                  className={cn(
                    "px-5 py-3 text-center tabular-nums",
                    row.winner === "react"
                      ? "text-[var(--hm-success)] font-semibold"
                      : "text-muted-foreground"
                  )}
                >
                  {row.react}
                </td>
                <td
                  className={cn(
                    "px-5 py-3 text-center tabular-nums",
                    row.winner === "reflection"
                      ? "text-[var(--hm-success)] font-semibold"
                      : "text-muted-foreground"
                  )}
                >
                  {row.reflection}
                </td>
                <td className="px-5 py-3 text-center">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      row.winner === "reflection"
                        ? "bg-[var(--hm-primary)]/10 text-[var(--hm-primary)]"
                        : "bg-[var(--hm-warning)]/10 text-[var(--hm-warning)]"
                    )}
                  >
                    {row.winner === "reflection" ? "Reflection" : "ReAct"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
