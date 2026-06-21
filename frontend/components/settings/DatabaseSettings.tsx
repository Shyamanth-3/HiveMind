import { StatusBadge } from "@/components/shared/StatusBadge";
import { mockSystemServices } from "@/lib/mockData";
import { Database, Info } from "lucide-react";

// =============================================================================
// DatabaseSettings — Supabase/Neon connection status
// =============================================================================

export function DatabaseSettings() {
  const pgService = mockSystemServices.find((s) => s.name === "PostgreSQL");

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-4">Database</h3>
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <Database className="h-5 w-5 text-[var(--hm-primary)]" />
            <div>
              <p className="text-sm font-semibold text-foreground">
                PostgreSQL
              </p>
              <p className="text-xs text-muted-foreground">
                Supabase / Neon
              </p>
            </div>
          </div>
          {pgService && (
            <StatusBadge status={pgService.status} />
          )}
        </div>

        {pgService?.details && (
          <p className="text-xs text-muted-foreground mb-3">
            {pgService.details}
          </p>
        )}

        {/* Connection fields */}
        <div className="space-y-3">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Connection URL
            </label>
            <div className="mt-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs text-muted-foreground">
              postgresql://••••••••@db.xxxxx.supabase.co:5432/postgres
            </div>
          </div>
        </div>

        {/* pgvector callout */}
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-[var(--hm-primary)]/20 bg-[var(--hm-primary)]/5 px-3 py-2.5">
          <Info className="h-3.5 w-3.5 text-[var(--hm-primary)] shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">pgvector</span> is
            enabled on this same instance — no separate vector database in v1.
          </p>
        </div>
      </div>
    </div>
  );
}
