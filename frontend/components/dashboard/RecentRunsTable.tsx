import { StatusBadge } from "@/components/shared/StatusBadge";
import { mockRuns } from "@/lib/mockData";

// =============================================================================
// RecentRunsTable — Dashboard table showing recent runs
// =============================================================================

function formatDuration(ms?: number): string {
  if (!ms) return "In progress";
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RecentRunsTable() {
  return (
    <div className="hm-glass rounded-xl p-5">
      <h3 className="text-sm font-semibold text-foreground mb-4">
        Recent Runs
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="pb-3 pr-4 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Run ID
              </th>
              <th className="pb-3 pr-4 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Goal
              </th>
              <th className="pb-3 pr-4 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Status
              </th>
              <th className="pb-3 pr-4 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Created
              </th>
              <th className="pb-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Duration
              </th>
            </tr>
          </thead>
          <tbody>
            {mockRuns.map((run) => (
              <tr
                key={run.id}
                className="border-b border-border/50 transition-colors hover:bg-[var(--hm-surface-elevated)]/50 cursor-pointer"
              >
                <td className="py-3 pr-4 font-mono text-xs text-muted-foreground">
                  {run.id}
                </td>
                <td className="py-3 pr-4 text-foreground max-w-[300px] truncate">
                  {run.goal}
                </td>
                <td className="py-3 pr-4">
                  <StatusBadge status={run.status} size="sm" />
                </td>
                <td className="py-3 pr-4 text-muted-foreground tabular-nums">
                  {formatDate(run.created_at)}
                </td>
                <td className="py-3 text-muted-foreground tabular-nums">
                  {formatDuration(run.duration_ms)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
