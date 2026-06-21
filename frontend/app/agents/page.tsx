"use client";

import { useState } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { AgentCard } from "@/components/agents/AgentCard";
import { AgentDetailPanel } from "@/components/agents/AgentDetailPanel";
import { mockAgentStatus } from "@/lib/mockData";
import type { AgentStatusData } from "@/types";

// =============================================================================
// Agents Page — Digital Workforce Monitoring
// =============================================================================

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<AgentStatusData | null>(
    null
  );

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Digital Workforce"
        subtitle="Exactly 5 agents — Queen, Architect, Scout, Builder, Guardian. Click any card to inspect its contract and activity."
      />

      {/* Agent Cards Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {mockAgentStatus.map((agent) => (
          <AgentCard
            key={agent.agent}
            data={agent}
            isSelected={selectedAgent?.agent === agent.agent}
            onClick={() =>
              setSelectedAgent(
                selectedAgent?.agent === agent.agent ? null : agent
              )
            }
          />
        ))}
      </div>

      {/* Detail Panel */}
      {selectedAgent && (
        <AgentDetailPanel
          data={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}