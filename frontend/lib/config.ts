// =============================================================================
// HiveMind — runtime endpoints
// Override with NEXT_PUBLIC_API_ORIGIN (e.g. https://api.example.com) for other environments.
// The WebSocket origin defaults to the API origin with http(s) -> ws(s).
// =============================================================================

export const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
export const API_BASE = `${API_ORIGIN}/api/v1`;
export const WS_ORIGIN =
  process.env.NEXT_PUBLIC_WS_ORIGIN ?? API_ORIGIN.replace(/^http/, "ws");

/** ws://host/ws/runs/{runId}[?last_event_id=...] — the run-scoped telemetry endpoint. */
export function runSocketUrl(runId: string, lastEventId?: string | null): string {
  const base = `${WS_ORIGIN}/ws/runs/${encodeURIComponent(runId)}`;
  return lastEventId ? `${base}?last_event_id=${encodeURIComponent(lastEventId)}` : base;
}
