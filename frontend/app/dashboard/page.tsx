"use client";

import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { MetricsRow } from "@/components/dashboard/MetricsRow";
import { CostBreakdownChart } from "@/components/dashboard/CostBreakdownChart";
import { RecentRunsTable } from "@/components/dashboard/RecentRunsTable";
import { EventFeed } from "@/components/dashboard/EventFeed";
import { AgentHealthGrid } from "@/components/dashboard/AgentHealthGrid";

// =============================================================================
// Dashboard Page — Command Center
// =============================================================================

export default function DashboardPage() {
  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <DashboardHero />
      <MetricsRow />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <CostBreakdownChart />
        </div>
        <div className="lg:col-span-2">
          <EventFeed />
        </div>
      </div>

      <AgentHealthGrid />
      <RecentRunsTable />
    </div>
  );
}