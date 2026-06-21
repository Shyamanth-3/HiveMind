import { mockMemoryChunks, mockProjects } from "@/lib/mockData";
import { Layers } from "lucide-react";

// =============================================================================
// MemoryChunkTable — Table of stored memory chunks
// =============================================================================

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getProjectName(projectId: string): string {
  return mockProjects.find((p) => p.id === projectId)?.name || projectId;
}

export function MemoryChunkTable() {
  return (
    <div className="hm-glass rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center gap-2">
        <Layers className="h-4 w-4 text-[var(--hm-primary)]" />
        <h3 className="text-sm font-semibold text-foreground">
          Memory Chunks
        </h3>
        <span className="text-xs text-muted-foreground">
          ({mockMemoryChunks.length} chunks)
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background/30">
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Content
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Project
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Source
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Dimensions
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Created
              </th>
            </tr>
          </thead>
          <tbody>
            {mockMemoryChunks.map((chunk) => (
              <tr
                key={chunk.id}
                className="border-b border-border/50 transition-colors hover:bg-[var(--hm-surface-elevated)]/50"
              >
                <td className="px-5 py-3 text-foreground max-w-[400px]">
                  <p className="truncate" title={chunk.content}>
                    {chunk.content}
                  </p>
                </td>
                <td className="px-5 py-3 text-muted-foreground whitespace-nowrap">
                  {getProjectName(chunk.project_id)}
                </td>
                <td className="px-5 py-3">
                  <span className="rounded-md bg-[var(--hm-primary)]/10 px-2 py-0.5 text-[10px] font-mono text-[var(--hm-primary)]">
                    {chunk.source}
                  </span>
                </td>
                <td className="px-5 py-3 text-muted-foreground font-mono text-xs">
                  {chunk.embedding_dimensions}d
                </td>
                <td className="px-5 py-3 text-muted-foreground tabular-nums whitespace-nowrap">
                  {formatDate(chunk.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
