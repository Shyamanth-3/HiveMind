"use client";

import { MetricCard } from "@/components/shared/MetricCard";
import { Activity, Users, CheckCircle, IndianRupee, Database } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { fetchRuns, fetchTasks, fetchMemoryChunks, fetchAgentStatuses, fetchCostSummary } from "@/lib/api";

// =============================================================================
// MetricsRow — 5 key metric cards for dashboard
// =============================================================================

export function MetricsRow() {
  const { data: runs } = useApi(fetchRuns);
  const { data: agentStatus } = useApi(fetchAgentStatuses);
  const { data: tasks } = useApi(fetchTasks);
  const { data: memoryChunks } = useApi(fetchMemoryChunks);
  const { data: costSummary } = useApi(fetchCostSummary);

  const activeRuns = (runs ?? []).filter((r) => r.status === "running").length;
  const agentsOnline = (agentStatus ?? []).filter(
    (a) => a.status === "online" || a.status === "working"
  ).length;

  const completedTasks = (tasks ?? []).filter(
    (t) => t.status === "completed" || t.status === "approved"
  ).length;
  const totalTasks = (tasks ?? []).length;
  const successRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const totalCostINR = (costSummary?.total_cost_usd ?? 0) * 83;
  const memoryCount = (memoryChunks ?? []).length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <MetricCard
        label="Active Runs"
        value={activeRuns}
        icon={Activity}
        iconColor="text-[var(--hm-primary)]"
      />
      <MetricCard
        label="Agents Online"
        value={`${agentsOnline} / 5`}
        icon={Users}
        iconColor="text-[var(--hm-success)]"
      />
      <MetricCard
        label="Task Success Rate"
        value={`${successRate}%`}
        icon={CheckCircle}
        trend={{ value: successRate > 80 ? 3 : -2, label: "vs target 80%" }}
        iconColor="text-[var(--hm-success)]"
      />
      <MetricCard
        label="Total Cost"
        value={`₹${totalCostINR.toFixed(2)}`}
        icon={IndianRupee}
        iconColor="text-[var(--hm-warning)]"
      />
      <MetricCard
        label="Memory Chunks"
        value={memoryCount}
        icon={Database}
        trend={{ value: 12, label: "this week" }}
        iconColor="text-[var(--hm-primary)]"
      />
    </div>
  );
}
