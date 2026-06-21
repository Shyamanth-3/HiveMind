"use client";

import { cn } from "@/lib/utils";
import { backendRoleToPersona, getPersonaIcon, getPersonaColor } from "@/lib/agentNames";
import type { BackendRoleKey, Task, TaskStatus } from "@/types";
import { ArrowRight, RotateCcw, PackageCheck } from "lucide-react";

// =============================================================================
// TaskGraphView — Renders the goal_to_deliverable workflow shape
// Queen → Architect → [Scout ‖ Builder] → Guardian → Store+Notify
// with the reject→Builder back-edge.
//
// Reusable: "live" mode (Runs) with task status, "template" mode (Workflow).
// =============================================================================

interface TaskGraphViewProps {
  tasks?: Task[];
  mode?: "live" | "template";
  className?: string;
}

interface GraphNode {
  id: string;
  role: BackendRoleKey | "store";
  label: string;
  status: TaskStatus | "idle";
  x: number;
  y: number;
  isParallel?: boolean;
}

interface GraphEdge {
  from: string;
  to: string;
  label?: string;
  isRejectLoop?: boolean;
}

function getStatusColor(status: TaskStatus | "idle"): string {
  switch (status) {
    case "completed":
    case "approved":
      return "var(--hm-success)";
    case "running":
      return "var(--hm-primary)";
    case "rejected":
      return "var(--hm-danger)";
    case "pending":
    case "idle":
    default:
      return "var(--border)";
  }
}

function getStatusBg(status: TaskStatus | "idle"): string {
  switch (status) {
    case "completed":
    case "approved":
      return "rgba(34, 197, 94, 0.08)";
    case "running":
      return "rgba(139, 92, 246, 0.08)";
    case "rejected":
      return "rgba(239, 68, 68, 0.08)";
    case "pending":
    case "idle":
    default:
      return "rgba(39, 39, 42, 0.3)";
  }
}

export function TaskGraphView({ tasks, mode = "live", className }: TaskGraphViewProps) {
  // Map tasks to nodes with status
  const tasksByType = new Map(tasks?.map((t) => [t.type, t]));

  const nodes: GraphNode[] = [
    {
      id: "queen",
      role: "ceo_agent",
      label: backendRoleToPersona.ceo_agent,
      status: tasksByType.get("plan")?.status || "idle",
      x: 60,
      y: 130,
    },
    {
      id: "architect",
      role: "pm_agent",
      label: backendRoleToPersona.pm_agent,
      status: tasksByType.get("breakdown")?.status || "idle",
      x: 220,
      y: 130,
    },
    {
      id: "scout",
      role: "research_agent",
      label: backendRoleToPersona.research_agent,
      status: tasksByType.get("research")?.status || "idle",
      x: 390,
      y: 65,
      isParallel: true,
    },
    {
      id: "builder",
      role: "developer_agent",
      label: backendRoleToPersona.developer_agent,
      status: tasksByType.get("build")?.status || "idle",
      x: 390,
      y: 195,
      isParallel: true,
    },
    {
      id: "guardian",
      role: "reviewer_qa_agent",
      label: backendRoleToPersona.reviewer_qa_agent,
      status: tasksByType.get("review")?.status || "idle",
      x: 560,
      y: 130,
    },
    {
      id: "store",
      role: "store",
      label: "Store + Notify",
      status: mode === "live" && tasks?.every((t) => t.status === "completed" || t.status === "approved") ? "completed" : "idle",
      x: 720,
      y: 130,
    },
  ];

  const edges: GraphEdge[] = [
    { from: "queen", to: "architect" },
    { from: "architect", to: "scout" },
    { from: "architect", to: "builder" },
    { from: "scout", to: "guardian" },
    { from: "builder", to: "guardian" },
    { from: "guardian", to: "store" },
    { from: "guardian", to: "builder", label: "reject", isRejectLoop: true },
  ];

  const hasRetry = tasks?.some((t) => t.retry_count > 0);

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox="0 0 820 270"
        className="w-full h-auto"
        style={{ minHeight: 200 }}
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth="8"
            markerHeight="6"
            refX="7"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="var(--muted-foreground)" opacity="0.5" />
          </marker>
          <marker
            id="arrowhead-danger"
            markerWidth="8"
            markerHeight="6"
            refX="7"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="var(--hm-danger)" opacity="0.7" />
          </marker>
        </defs>

        {/* Parallel bracket labels */}
        <text x="390" y="28" textAnchor="middle" fill="var(--muted-foreground)" fontSize="10" fontStyle="italic">
          parallel
        </text>

        {/* Edges */}
        {edges.map((edge) => {
          const from = nodes.find((n) => n.id === edge.from)!;
          const to = nodes.find((n) => n.id === edge.to)!;

          if (edge.isRejectLoop) {
            // Draw curved back-edge from Guardian to Builder
            const startX = from.x + 40;
            const startY = from.y + 25;
            const endX = to.x + 40;
            const endY = to.y + 25;
            return (
              <g key={`${edge.from}-${edge.to}-reject`}>
                <path
                  d={`M ${startX} ${startY} C ${startX + 30} ${startY + 60}, ${endX + 30} ${endY + 60}, ${endX} ${endY}`}
                  fill="none"
                  stroke={hasRetry ? "var(--hm-danger)" : "var(--hm-danger)"}
                  strokeWidth="1.5"
                  strokeDasharray={hasRetry ? "none" : "4 4"}
                  opacity={hasRetry ? 0.8 : 0.3}
                  markerEnd="url(#arrowhead-danger)"
                />
                <text
                  x={(startX + endX) / 2 + 30}
                  y={(startY + endY) / 2 + 50}
                  textAnchor="middle"
                  fill="var(--hm-danger)"
                  fontSize="9"
                  opacity={hasRetry ? 0.9 : 0.4}
                >
                  reject
                </text>
              </g>
            );
          }

          // Straight edges
          const startX = from.x + 80;
          const startY = from.y + 20;
          const endX = to.x;
          const endY = to.y + 20;

          return (
            <line
              key={`${edge.from}-${edge.to}`}
              x1={startX}
              y1={startY}
              x2={endX}
              y2={endY}
              stroke="var(--muted-foreground)"
              strokeWidth="1"
              opacity="0.3"
              markerEnd="url(#arrowhead)"
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const isStore = node.role === "store";
          const color = isStore ? "var(--muted-foreground)" : getPersonaColor(node.role as BackendRoleKey);
          const statusColor = getStatusColor(node.status);
          const statusBg = getStatusBg(node.status);
          const Icon = isStore ? PackageCheck : getPersonaIcon(node.role as BackendRoleKey);

          return (
            <g key={node.id}>
              {/* Node background */}
              <rect
                x={node.x}
                y={node.y}
                width={80}
                height={40}
                rx={8}
                fill={statusBg}
                stroke={statusColor}
                strokeWidth={node.status === "running" ? 2 : 1}
                className={node.status === "running" ? "animate-hm-node-running" : ""}
              />
              {/* Icon */}
              <foreignObject x={node.x + 6} y={node.y + 8} width={24} height={24}>
                <div className="flex items-center justify-center h-full">
                  <Icon
                    className="h-3.5 w-3.5"
                    style={{ color }}
                  />
                </div>
              </foreignObject>
              {/* Label */}
              <text
                x={node.x + 32}
                y={node.y + 24}
                fill="var(--foreground)"
                fontSize={isStore ? 9 : 10}
                fontWeight="600"
              >
                {node.label}
              </text>
            </g>
          );
        })}

        {/* Retry indicator */}
        {hasRetry && (
          <g>
            <foreignObject x={620} y={222} width={120} height={28}>
              <div className="flex items-center gap-1.5 rounded-md bg-[var(--hm-danger)]/10 px-2 py-1">
                <RotateCcw className="h-3 w-3 text-[var(--hm-danger)]" />
                <span className="text-[10px] font-medium text-[var(--hm-danger)]">
                  Retry cycle detected
                </span>
              </div>
            </foreignObject>
          </g>
        )}
      </svg>
    </div>
  );
}
