// =============================================================================
// HiveMind — WebSocket telemetry message contract (mirrors backend app/telemetry/contract.py)
// =============================================================================

export const AGENT_IDS = ["queen", "architect", "scout", "builder", "guardian"] as const;
export type AgentId = (typeof AGENT_IDS)[number];

export type AgentStatus = "pending" | "running" | "completed" | "failed" | "revision";

export interface AgentState {
  status: AgentStatus;
  /** revision number the agent last worked on / reviewed (0 = original output) */
  revision: number;
  verdict?: string | null;
  error_type?: string | null;
}

export type RunStatus = "running" | "completed" | "failed";

export interface SafeFailure {
  failed_stage: string;
  error_type: string;
  message: string;
  verdict?: string | null;
  revision_count?: number | null;
  max_revisions?: number | null;
}

export interface WorkflowState {
  run_id: string;
  status: RunStatus;
  is_completed: boolean;
  current_stage: string | null;
  revision: { count: number; max: number; current: number; status: string };
  agents: Record<AgentId, AgentState>;
  failure: SafeFailure | null;
  last_event_id: string | null;
}

export interface TelemetryEvent {
  type: "workflow.event";
  /** dedup key: an event_id is applied at most once */
  event_id: string;
  event_type: string;
  run_id: string;
  timestamp: string;
  source: string | null;
  revision_number: number | null;
  /** compact, backend-sanitised summary (never the raw Kafka payload) */
  payload: Record<string, unknown>;
}

export interface SnapshotMessage {
  type: "workflow.snapshot";
  /** full = whole history; resume = only events after the client's last_event_id */
  mode: "full" | "resume";
  run_id: string;
  state: WorkflowState;
  events: TelemetryEvent[];
  last_event_id: string | null;
}

export interface StateMessage {
  type: "workflow.state";
  run_id: string;
  state: WorkflowState;
}

export interface HeartbeatMessage {
  type: "heartbeat";
  ts: string;
}

export interface PongMessage {
  type: "pong";
}

export type ServerMessage =
  | SnapshotMessage
  | TelemetryEvent
  | StateMessage
  | HeartbeatMessage
  | PongMessage;

/**
 * Transport state only. It says nothing about the workflow: a dropped socket is "reconnecting",
 * never "failed". Workflow failure comes exclusively from a run.failed event / state.status.
 */
export type ConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";
