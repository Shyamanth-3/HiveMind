// =============================================================================
// HiveMind — Type Definitions
// Mirrors the backend data model exactly so wiring to FastAPI + WebSocket is
// a drop-in, not a rewrite. All agent references use backend role keys;
// persona names are resolved at the presentation layer via lib/agentNames.ts.
// =============================================================================

// ---------------------------------------------------------------------------
// Agent & Status Enums
// ---------------------------------------------------------------------------

/** Backend role keys — the canonical agent identifiers in all stored/transmitted data */
export type BackendRoleKey =
  | "ceo_agent"
  | "pm_agent"
  | "research_agent"
  | "developer_agent"
  | "reviewer_qa_agent";

/** Presentation-layer persona names — resolved from BackendRoleKey */
export type AgentPersona =
  | "Queen"
  | "Architect"
  | "Scout"
  | "Builder"
  | "Guardian";

/** Canonical event types — use these exact strings, never invented ones */
export type EventType =
  | "run_created"
  | "plan_ready"
  | "tasks_created"
  | "task_runnable"
  | "task_completed"
  | "task_rejected"
  | "task_approved"
  | "run_completed";

/** Run status */
export type RunStatus = "running" | "completed" | "failed";

/** Task status */
export type TaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "rejected"
  | "approved";

/** Agent operational status */
export type AgentOperationalStatus = "online" | "idle" | "working";

/** Infrastructure service status — includes cold-start for free-tier services */
export type ServiceStatus = "online" | "offline" | "cold-start" | "degraded";

/** Agent log outcome */
export type AgentLogOutcome = "success" | "retried" | "failed";

/** All possible status values for the universal StatusBadge component */
export type StatusValue =
  | "online"
  | "offline"
  | "idle"
  | "working"
  | "running"
  | "pending"
  | "completed"
  | "approved"
  | "rejected"
  | "failed"
  | "cold-start"
  | "degraded";

// ---------------------------------------------------------------------------
// Core Data Models
// ---------------------------------------------------------------------------

/** Project — a top-level container for runs */
export interface Project {
  id: string;
  name: string;
  owner: string;
  created_at: string;
  goal_summary: string;
}

/** Run — a single execution of the goal_to_deliverable workflow */
export interface Run {
  id: string;
  project_id: string;
  goal: string;
  plan_text: string;
  status: RunStatus;
  success_criteria: string[];
  created_at: string;
  duration_ms?: number;
}

/** Task — a single unit of work assigned to an agent within a run */
export interface Task {
  id: string;
  run_id: string;
  type: string;
  assigned_agent: BackendRoleKey;
  depends_on: string[];
  status: TaskStatus;
  result?: string;
  retry_count: number;
}

/** Event — audit log entry from the Redis pub/sub event stream */
export interface Event {
  id: string;
  run_id: string;
  event_type: EventType;
  agent?: BackendRoleKey;
  payload: Record<string, unknown>;
  cost_usd: number;
  latency_ms: number;
  created_at: string;
}

/** MemoryChunk — a piece of knowledge stored in pgvector */
export interface MemoryChunk {
  id: string;
  project_id: string;
  content: string;
  embedding_dimensions: number;
  source: string;
  created_at: string;
  similarity_score?: number;
}

// ---------------------------------------------------------------------------
// Observability / Monitoring
// ---------------------------------------------------------------------------

/** AgentLog — what every agent call logs, the basis for observability views */
export interface AgentLog {
  run_id: string;
  task_id: string;
  agent: BackendRoleKey;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
  outcome: AgentLogOutcome;
  model: string;
}

/** AgentStatus — live operational status for each agent */
export interface AgentStatusData {
  agent: BackendRoleKey;
  status: AgentOperationalStatus;
  current_task: string | null;
  last_activity: string;
  tasks_completed: number;
  success_rate: number;
}

/** SystemService — infrastructure health status */
export interface SystemService {
  name: string;
  status: ServiceStatus;
  latency_ms?: number;
  details?: string;
}

// ---------------------------------------------------------------------------
// LLM Provider (Settings)
// ---------------------------------------------------------------------------

export interface LLMProvider {
  id: string;
  name: string;
  model: string;
  status: "active" | "available" | "fallback";
  tier: string;
  api_key_set: boolean;
  badge?: string;
}
