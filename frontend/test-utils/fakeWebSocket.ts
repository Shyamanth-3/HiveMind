// Controllable WebSocket stand-in for unit tests (no network).
import type { ServerMessage, TelemetryEvent, WorkflowState, AgentId, AgentState } from "@/lib/telemetry/types";

export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static reset() {
    FakeWebSocket.instances = [];
  }
  static get last(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }

  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  readyState = 0;
  closedByClient: { code?: number; reason?: string } | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close(code?: number, reason?: string) {
    if (this.readyState === 3) return;
    this.closedByClient = { code, reason };
    this.readyState = 3;
    this.onclose?.({ code: code ?? 1005, reason: reason ?? "", wasClean: true } as CloseEvent);
  }

  // ── test controls (the "server") ──
  open() {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }
  message(msg: ServerMessage | Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
  }
  raw(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
  serverClose(code = 1006, reason = "") {
    this.readyState = 3;
    this.onclose?.({ code, reason, wasClean: code === 1000 } as CloseEvent);
  }
}

export const asWebSocket = FakeWebSocket as unknown as typeof WebSocket;

// ── message builders ──

const AGENTS: AgentId[] = ["queen", "architect", "scout", "builder", "guardian"];

export function agents(overrides: Partial<Record<AgentId, Partial<AgentState>>> = {}): Record<AgentId, AgentState> {
  const base = Object.fromEntries(AGENTS.map((a) => [a, { status: "pending", revision: 0 }])) as Record<AgentId, AgentState>;
  for (const [k, v] of Object.entries(overrides)) base[k as AgentId] = { ...base[k as AgentId], ...v } as AgentState;
  return base;
}

export function state(over: Partial<WorkflowState> = {}): WorkflowState {
  return {
    run_id: "run-1",
    status: "running",
    is_completed: false,
    current_stage: "run.created",
    revision: { count: 0, max: 3, current: 0, status: "none" },
    agents: agents(),
    failure: null,
    last_event_id: null,
    ...over,
  };
}

let seq = 0;
export function evt(event_type: string, over: Partial<TelemetryEvent> = {}): TelemetryEvent {
  seq += 1;
  return {
    type: "workflow.event",
    event_id: over.event_id ?? `evt-${seq}`,
    event_type,
    run_id: "run-1",
    timestamp: new Date(2026, 8, 24, 10, 0, seq).toISOString(),
    source: null,
    revision_number: null,
    payload: {},
    ...over,
  };
}

export function snapshot(events: TelemetryEvent[], over: Record<string, unknown> = {}) {
  return {
    type: "workflow.snapshot" as const,
    mode: "full" as const,
    run_id: "run-1",
    state: state(),
    events,
    last_event_id: events.length ? events[events.length - 1].event_id : null,
    ...over,
  };
}

export function stateMsg(s: WorkflowState) {
  return { type: "workflow.state" as const, run_id: s.run_id, state: s };
}
