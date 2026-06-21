import { StatusBadge } from "@/components/shared/StatusBadge";
import { mockSystemServices } from "@/lib/mockData";
import { Radio } from "lucide-react";

// =============================================================================
// RedisSettings — Upstash connection status with usage split
// =============================================================================

const usageSplit = [
  { label: "Pub/Sub", usage: "1,247 messages/day", percentage: 45 },
  { label: "Queues", usage: "380 jobs/day", percentage: 30 },
  { label: "Cache", usage: "156 hits/day", percentage: 25 },
];

export function RedisSettings() {
  const redisService = mockSystemServices.find((s) => s.name === "Redis");

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-4">Redis</h3>
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <Radio className="h-5 w-5 text-[var(--hm-success)]" />
            <div>
              <p className="text-sm font-semibold text-foreground">Redis</p>
              <p className="text-xs text-muted-foreground">Upstash</p>
            </div>
          </div>
          {redisService && <StatusBadge status={redisService.status} />}
        </div>

        {redisService?.details && (
          <p className="text-xs text-muted-foreground mb-4">
            {redisService.details}
          </p>
        )}

        {/* Usage Split */}
        <div className="space-y-3">
          {usageSplit.map((item) => (
            <div key={item.label}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-foreground">
                  {item.label}
                </span>
                <span className="text-[10px] text-muted-foreground tabular-nums">
                  {item.usage}
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--hm-success)] transition-all duration-500"
                  style={{ width: `${item.percentage}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Connection */}
        <div className="mt-4">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Connection URL
          </label>
          <div className="mt-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs text-muted-foreground">
            rediss://••••••••@upstash-xxxxx.upstash.io:6379
          </div>
        </div>
      </div>
    </div>
  );
}
