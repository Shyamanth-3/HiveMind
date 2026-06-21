// =============================================================================
// HiveMind — Agent Persona Mapping
// Single source of truth: backend role key <-> presentation persona name.
// Every component takes a BackendRoleKey prop and resolves the display name,
// icon, color, and description through this module.
// =============================================================================

import {
  Crown,
  Compass,
  Binoculars,
  Hammer,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { BackendRoleKey, AgentPersona } from "@/types";

// ---------------------------------------------------------------------------
// Core Mappings
// ---------------------------------------------------------------------------

export const backendRoleToPersona: Record<BackendRoleKey, AgentPersona> = {
  ceo_agent: "Queen",
  pm_agent: "Architect",
  research_agent: "Scout",
  developer_agent: "Builder",
  reviewer_qa_agent: "Guardian",
};

export const personaToBackendRole: Record<AgentPersona, BackendRoleKey> = {
  Queen: "ceo_agent",
  Architect: "pm_agent",
  Scout: "research_agent",
  Builder: "developer_agent",
  Guardian: "reviewer_qa_agent",
};

// ---------------------------------------------------------------------------
// Icons — Lucide icon per persona, used consistently across all surfaces
// ---------------------------------------------------------------------------

const personaIcons: Record<BackendRoleKey, LucideIcon> = {
  ceo_agent: Crown,
  pm_agent: Compass,
  research_agent: Binoculars,
  developer_agent: Hammer,
  reviewer_qa_agent: ShieldCheck,
};

export function getPersonaIcon(role: BackendRoleKey): LucideIcon {
  return personaIcons[role];
}

// ---------------------------------------------------------------------------
// Colors — unique accent per agent for charts, avatars, graph nodes
// ---------------------------------------------------------------------------

const personaColors: Record<BackendRoleKey, string> = {
  ceo_agent: "#F59E0B",       // Amber — regal / commanding
  pm_agent: "#3B82F6",        // Blue — structured / planning
  research_agent: "#22C55E",  // Green — discovery / exploration
  developer_agent: "#8B5CF6", // Purple — creative / building
  reviewer_qa_agent: "#EF4444", // Red — protective / gatekeeping
};

export function getPersonaColor(role: BackendRoleKey): string {
  return personaColors[role];
}

// ---------------------------------------------------------------------------
// Descriptions — one-line job descriptions from the ground truth table
// ---------------------------------------------------------------------------

const personaDescriptions: Record<BackendRoleKey, string> = {
  ceo_agent:
    "Turns a raw goal into a plan + 3–5 measurable success criteria. Publishes plan_ready.",
  pm_agent:
    "Turns the plan into a task graph with dependencies. Publishes tasks_created.",
  research_agent:
    "Gathers context/facts via web-search tool calls, writes findings to memory.",
  developer_agent:
    "Produces the actual code/content deliverable, grounded in RAG context.",
  reviewer_qa_agent:
    "Checks output against the Queen's success criteria; approves or rejects with structured feedback.",
};

export function getPersonaDescription(role: BackendRoleKey): string {
  return personaDescriptions[role];
}

// ---------------------------------------------------------------------------
// Input/Output Contracts — for the Agent Detail Panel
// ---------------------------------------------------------------------------

export interface AgentContract {
  inputs: string[];
  outputs: string[];
  publishes: string[];
}

const agentContracts: Record<BackendRoleKey, AgentContract> = {
  ceo_agent: {
    inputs: ["Raw goal from user"],
    outputs: ["Structured plan", "3–5 measurable success criteria"],
    publishes: ["plan_ready"],
  },
  pm_agent: {
    inputs: ["Queen's plan + success criteria"],
    outputs: ["Task graph with dependencies"],
    publishes: ["tasks_created"],
  },
  research_agent: {
    inputs: ["Task requiring context", "Existing memory chunks"],
    outputs: ["Research findings written to memory"],
    publishes: ["task_completed"],
  },
  developer_agent: {
    inputs: ["Task spec", "RAG context from memory", "Scout's research findings"],
    outputs: ["Code/content deliverable"],
    publishes: ["task_completed"],
  },
  reviewer_qa_agent: {
    inputs: ["Completed task output", "Queen's success criteria"],
    outputs: ["task_approved OR task_rejected + structured feedback"],
    publishes: ["task_approved", "task_rejected"],
  },
};

export function getAgentContract(role: BackendRoleKey): AgentContract {
  return agentContracts[role];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export const ALL_BACKEND_ROLES: BackendRoleKey[] = [
  "ceo_agent",
  "pm_agent",
  "research_agent",
  "developer_agent",
  "reviewer_qa_agent",
];

export function getPersonaName(role: BackendRoleKey): AgentPersona {
  return backendRoleToPersona[role];
}
