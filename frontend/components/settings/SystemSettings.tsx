"use client";

import { useState } from "react";
import { RotateCcw, IndianRupee } from "lucide-react";

// =============================================================================
// SystemSettings — Retry cap and cost alert threshold
// =============================================================================

export function SystemSettings() {
  const [retryCap, setRetryCap] = useState(3);
  const [costThreshold, setCostThreshold] = useState(50);

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-4">
        System Settings
      </h3>
      <div className="rounded-xl border border-border bg-card p-5 space-y-5">
        {/* Retry Cap */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <RotateCcw className="h-4 w-4 text-[var(--hm-danger)]" />
            <label className="text-sm font-medium text-foreground">
              Guardian Rejection Retry Cap
            </label>
          </div>
          <p className="text-xs text-muted-foreground mb-2">
            Maximum times Builder can retry after Guardian rejection before
            marking the task as failed.
          </p>
          <div className="flex items-center gap-3">
            <input
              type="number"
              min={1}
              max={10}
              value={retryCap}
              onChange={(e) => setRetryCap(parseInt(e.target.value) || 1)}
              className="h-9 w-20 rounded-lg border border-border bg-background px-3 text-sm text-foreground text-center tabular-nums focus:border-[var(--hm-primary)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--hm-primary)]/30"
            />
            <span className="text-xs text-muted-foreground">retries</span>
          </div>
        </div>

        {/* Cost Alert */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <IndianRupee className="h-4 w-4 text-[var(--hm-warning)]" />
            <label className="text-sm font-medium text-foreground">
              Cost Alert Threshold
            </label>
          </div>
          <p className="text-xs text-muted-foreground mb-2">
            Get notified when cumulative run costs exceed this amount.
          </p>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">₹</span>
            <input
              type="number"
              min={1}
              value={costThreshold}
              onChange={(e) => setCostThreshold(parseInt(e.target.value) || 1)}
              className="h-9 w-24 rounded-lg border border-border bg-background px-3 text-sm text-foreground text-center tabular-nums focus:border-[var(--hm-primary)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--hm-primary)]/30"
            />
            <span className="text-xs text-muted-foreground">INR</span>
          </div>
        </div>
      </div>
    </div>
  );
}
