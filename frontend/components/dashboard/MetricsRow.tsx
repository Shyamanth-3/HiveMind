import { MetricCard } from "@/components/shared/MetricCard";
import { Activity, Users, CheckCircle, IndianRupee, Database } from "lucide-react";
import { mockRuns, mockAgentStatus, mockTasks, mockMemoryChunks, getTotalCostINR } from "@/lib/mockData";

// =============================================================================
// MetricsRow — 5 key metric cards for dashboard
// =============================================================================

export function MetricsRow() {
  const activeRuns = mockRuns.filter((r) => r.status === "running").length;
  const agentsOnline = mockAgentStatus.filter(
    (a) => a.status === "online" || a.status === "working"
  ).length;

  const completedTasks = mockTasks.filter(
    (t) => t.status === "completed" || t.status === "approved"
  ).length;
  const totalTasks = mockTasks.length;
  const successRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const totalCost = getTotalCostINR();
  const memoryChunks = mockMemoryChunks.length;

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
        value={`₹${totalCost.toFixed(2)}`}
        icon={IndianRupee}
        iconColor="text-[var(--hm-warning)]"
      />
      <MetricCard
        label="Memory Chunks"
        value={memoryChunks}
        icon={Database}
        trend={{ value: 12, label: "this week" }}
        iconColor="text-[var(--hm-primary)]"
      />
    </div>
  );
}
