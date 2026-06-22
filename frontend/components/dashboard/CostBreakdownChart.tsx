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
import { backendRoleToPersona } from "@/lib/agentNames";
import type { BackendRoleKey } from "@/types";
import { Sparkles, Settings } from "lucide-react";

// =============================================================================
// CostBreakdownChart — Bar chart showing cost per agent persona in ₹
// =============================================================================

export function CostBreakdownChart() {
  const costByAgent = getCostByAgent();

  const data = Object.entries(costByAgent).map(([role, cost]) => ({
    name: backendRoleToPersona[role as BackendRoleKey],
    cost: Math.round(cost * 100) / 100,
    role,
  }));

  return (
    <div className="bg-[var(--hm-surface)] border border-border rounded-xl p-5 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[14px] font-semibold text-foreground">
          Cost Breakdown
        </h3>
        
        {/* AI Insight Bar */}
        <div className="flex items-center gap-[10px] bg-[#2a2a2a] border border-[#3a3a3a] rounded-lg px-[12px] py-[10px]">
          <Sparkles className="h-4 w-4 text-[var(--hm-primary)]" />
          <span className="text-[12px] text-gray-300">
            Developer agent generated highest cost
          </span>
          <Settings className="h-4 w-4 text-[#666666] ml-2 cursor-pointer hover:text-white transition-colors" />
        </div>
      </div>
      
      <div className="flex-1 min-h-[250px]">
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
              cursor={{ fill: "rgba(232, 130, 42, 0.05)" }}
            />
            <Bar dataKey="cost" radius={[6, 6, 0, 0]} maxBarSize={48}>
              {data.map((entry, index) => (
                <Cell 
                  key={entry.role} 
                  fill="var(--hm-primary)" 
                  fillOpacity={0.6 + (index * 0.1)} 
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
