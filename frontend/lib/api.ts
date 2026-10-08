// =============================================================================
// HiveMind — API Client
// Central typed fetch layer for all backend endpoints.
// Every component imports from here instead of mockData.ts.
// =============================================================================

import type {
  Project,
  Run,
  Task,
  Event,
  MemoryChunk,
  AgentStatusData,
  AgentLog,
  SystemService,
} from "@/types";

import { API_BASE } from "@/lib/config";
import { UnauthorizedError, redirectToLogin } from "@/lib/auth";

async function apiFetch<T>(path: string): Promise<T> {
  // The session is an httpOnly cookie: send it, never handle a token in JavaScript.
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (res.status === 401) {
    redirectToLogin(); // expired / missing session: sign in again
    throw new UnauthorizedError();
  }
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export function fetchProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects/");
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function fetchRuns(projectId?: string): Promise<Run[]> {
  const query = projectId ? `?project_id=${projectId}` : "";
  return apiFetch<Run[]>(`/runs/${query}`);
}

export function fetchRun(runId: string): Promise<Run> {
  return apiFetch<Run>(`/runs/${runId}`);
}

export function fetchWorkflowStatus(runId: string): Promise<unknown> {
  return apiFetch<unknown>(`/workflow/${runId}/status`);
}

export function fetchWorkflowOutputs(runId: string): Promise<unknown> {
  return apiFetch<unknown>(`/workflow/${runId}/outputs`);
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export function fetchTasks(): Promise<Task[]> {
  return apiFetch<Task[]>("/tasks/");
}

export function fetchTasksByRun(runId: string): Promise<Task[]> {
  return apiFetch<Task[]>(`/tasks/?run_id=${runId}`);
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export function fetchRecentEvents(limit = 20): Promise<Event[]> {
  return apiFetch<Event[]>(`/events/recent?limit=${limit}`);
}

export function fetchEventsByRun(runId: string): Promise<Event[]> {
  return apiFetch<Event[]>(`/events/?run_id=${runId}`);
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

export function fetchMemoryChunks(projectId?: string): Promise<MemoryChunk[]> {
  const query = projectId ? `?project_id=${projectId}` : "";
  return apiFetch<MemoryChunk[]>(`/memory/${query}`);
}

// ---------------------------------------------------------------------------
// Agent Logs & Cost
// ---------------------------------------------------------------------------

export interface CostSummary {
  total_cost_usd: number;
  by_agent: Record<string, number>;
}

export function fetchCostSummary(): Promise<CostSummary> {
  return apiFetch<CostSummary>("/agent-logs/cost-summary");
}

export function fetchAgentLogsByRun(runId: string): Promise<AgentLog[]> {
  return apiFetch<AgentLog[]>(`/agent-logs/?run_id=${runId}`);
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export function fetchAgentStatuses(): Promise<AgentStatusData[]> {
  return apiFetch<AgentStatusData[]>("/system/agents");
}

export function fetchSystemServices(): Promise<SystemService[]> {
  return apiFetch<SystemService[]>("/system/services");
}
