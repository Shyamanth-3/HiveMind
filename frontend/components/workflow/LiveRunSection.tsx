"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/hooks/useApi";
import { fetchRuns } from "@/lib/api";
import { LiveRunPanel } from "./LiveRunPanel";

// =============================================================================
// LiveRunSection — pick a run (or deep-link with ?run=<id>) and watch it live over WebSocket.
// =============================================================================

export function LiveRunSection() {
  const params = useSearchParams();
  const { data: runs, loading, error } = useApi(() => fetchRuns(), []);
  const [picked, setPicked] = useState<string | null>(null);

  const requested = params.get("run");
  const selected = picked ?? requested ?? runs?.[0]?.id ?? null;

  return (
    <div className="space-y-3" data-testid="live-run-section">
      <div className="flex items-center gap-3">
        <label htmlFor="live-run-select" className="text-[12px] text-muted-foreground">
          Run
        </label>
        <select
          id="live-run-select"
          data-testid="run-select"
          value={selected ?? ""}
          onChange={(e) => setPicked(e.target.value)}
          className="bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-2 py-1 text-[12px] text-white max-w-[520px]"
        >
          {requested && !runs?.some((r) => r.id === requested) && <option value={requested}>{requested}</option>}
          {(runs ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {r.status} · {r.goal.slice(0, 70)} · {r.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </div>
      {selected ? (
        <LiveRunPanel key={selected} runId={selected} />
      ) : (
        <p className="text-[12px] text-muted-foreground">
          {loading ? "Loading runs…" : error ? `Could not load runs: ${error}` : "No runs yet."}
        </p>
      )}
    </div>
  );
}
