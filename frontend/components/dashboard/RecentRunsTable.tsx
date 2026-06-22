import { StatusBadge } from "@/components/shared/StatusBadge";
import { mockRuns } from "@/lib/mockData";
import { Search, Plus, MoreHorizontal } from "lucide-react";

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
    <div className="bg-[var(--hm-surface)] border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-[14px] font-semibold text-white">
          Recent Runs
        </h3>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search runs..." 
              className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg pl-9 pr-3 py-1.5 text-sm text-white focus:outline-none focus:border-[var(--hm-primary)] w-[200px]"
            />
          </div>
          <button className="flex items-center gap-2 bg-[var(--hm-primary)] text-white hover:bg-[var(--hm-primary)]/90 transition-colors px-3 py-1.5 rounded-lg text-sm font-medium">
            <Plus className="h-4 w-4" />
            New Run
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="pb-3 pr-4 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Run ID
              </th>
              <th className="pb-3 pr-4 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Goal
              </th>
              <th className="pb-3 pr-4 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Status
              </th>
              <th className="pb-3 pr-4 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Created
              </th>
              <th className="pb-3 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Duration
              </th>
              <th className="pb-3 text-right text-[10px] font-bold uppercase tracking-[0.1em] text-[#666666]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {mockRuns.map((run) => (
              <tr
                key={run.id}
                className="border-b border-border/50 transition-colors hover:bg-[#2a2a2a]/50 cursor-pointer group"
              >
                <td className="py-4 pr-4 font-mono text-[12px] text-muted-foreground">
                  {run.id}
                </td>
                <td className="py-4 pr-4 text-white font-medium max-w-[300px] truncate text-[14px]">
                  {run.goal}
                </td>
                <td className="py-4 pr-4">
                  <StatusBadge status={run.status} size="sm" />
                </td>
                <td className="py-4 pr-4 text-[#9ca3af] tabular-nums text-[14px]">
                  {formatDate(run.created_at)}
                </td>
                <td className="py-4 text-[#9ca3af] tabular-nums text-[14px]">
                  {formatDuration(run.duration_ms)}
                </td>
                <td className="py-4 text-right">
                  <button className="text-muted-foreground hover:text-white p-1 rounded transition-colors opacity-0 group-hover:opacity-100">
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
