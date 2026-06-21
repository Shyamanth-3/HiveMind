"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { getCostByAgent } from "@/lib/mockData";
import { backendRoleToPersona, getPersonaColor } from "@/lib/agentNames";
import type { BackendRoleKey } from "@/types";

// =============================================================================
// CostBreakdownChart — Bar chart showing cost per agent persona in ₹
// =============================================================================

export function CostBreakdownChart() {
  const costByAgent = getCostByAgent();

  const data = Object.entries(costByAgent).map(([role, cost]) => ({
    name: backendRoleToPersona[role as BackendRoleKey],
    cost: Math.round(cost * 100) / 100,
    color: getPersonaColor(role as BackendRoleKey),
    role,
  }));

  return (
    <div className="hm-glass rounded-xl p-5">
      <h3 className="text-sm font-semibold text-foreground mb-4">
        Cost by Agent
      </h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--border)"
              vertical={false}
            />
            <XAxis
              dataKey="name"
              tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              tickFormatter={(value: number) => `₹${value}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--hm-surface-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                color: "var(--foreground)",
                fontSize: "12px",
              }}
              formatter={(value) => [`₹${Number(value).toFixed(2)}`, "Cost"]}
              cursor={{ fill: "rgba(139, 92, 246, 0.05)" }}
            />
            <Bar dataKey="cost" radius={[6, 6, 0, 0]} maxBarSize={48}>
              {data.map((entry) => (
                <Cell key={entry.role} fill={entry.color} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
