import { MetricCard } from "@/components/shared/MetricCard";
import { Database, HardDrive, TrendingUp } from "lucide-react";
import { mockMemoryChunks } from "@/lib/mockData";

// =============================================================================
// KnowledgeStats — Memory statistics cards
// =============================================================================

export function KnowledgeStats() {
  const totalChunks = mockMemoryChunks.length;
  // Approximate storage: ~1KB per chunk (content + embedding)
  const storageUsedMB = (totalChunks * 1.2) / 1; // ~1.2KB per chunk → MB approx
  const storageDisplay = storageUsedMB < 1 ? `${Math.round(storageUsedMB * 1024)}KB` : `${storageUsedMB.toFixed(1)}MB`;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <MetricCard
        label="Total Chunks"
        value={totalChunks}
        icon={Database}
        iconColor="text-[var(--hm-primary)]"
      />
      <MetricCard
        label="Storage Used"
        value={`${storageDisplay} / 500MB`}
        icon={HardDrive}
        trend={{ value: 2, label: "free tier limit" }}
        iconColor="text-[var(--hm-success)]"
      />
      <MetricCard
        label="Retrieved This Week"
        value={14}
        icon={TrendingUp}
        trend={{ value: 8, label: "vs last week" }}
        iconColor="text-[var(--hm-warning)]"
      />
    </div>
  );
}
