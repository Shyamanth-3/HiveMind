"use client";

import { cn } from "@/lib/utils";
import { mockLLMProviders } from "@/lib/mockData";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Eye, EyeOff, Cpu, Zap } from "lucide-react";
import { useState } from "react";

// =============================================================================
// LLMProviderCards — Swappable LLM provider cards with masked API keys
// =============================================================================

export function LLMProviderCards() {
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set());

  const toggleKey = (id: string) => {
    setRevealedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-4">
        LLM Providers
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {mockLLMProviders.map((provider) => (
          <div
            key={provider.id}
            className={cn(
              "rounded-xl border p-5 transition-all duration-300",
              provider.status === "active"
                ? "border-[var(--hm-primary)]/30 bg-[var(--hm-primary)]/5"
                : "border-border bg-card"
            )}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div
                  className={cn(
                    "rounded-lg p-2",
                    provider.status === "active"
                      ? "bg-[var(--hm-primary)]/10"
                      : "bg-muted"
                  )}
                >
                  {provider.status === "fallback" ? (
                    <Cpu className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Zap
                      className={cn(
                        "h-4 w-4",
                        provider.status === "active"
                          ? "text-[var(--hm-primary)]"
                          : "text-muted-foreground"
                      )}
                    />
                  )}
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {provider.name}
                  </p>
                  <p className="text-xs text-muted-foreground font-mono">
                    {provider.model}
                  </p>
                </div>
              </div>
              {provider.badge && (
                <StatusBadge
                  status={
                    provider.status === "active"
                      ? "online"
                      : provider.status === "fallback"
                      ? "idle"
                      : "pending"
                  }
                  size="sm"
                />
              )}
            </div>

            {/* Tier */}
            <p className="text-xs text-muted-foreground mb-3">
              {provider.tier}
              {provider.badge && (
                <span className="ml-2 text-[var(--hm-primary)]">
                  · {provider.badge}
                </span>
              )}
            </p>

            {/* API Key */}
            <div className="flex items-center gap-2">
              <div className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs">
                {provider.api_key_set ? (
                  revealedKeys.has(provider.id) ? (
                    <span className="text-muted-foreground">
                      sk-...{provider.id.slice(0, 4)}xxxx
                    </span>
                  ) : (
                    <span className="text-muted-foreground">••••••••••••</span>
                  )
                ) : (
                  <span className="text-muted-foreground/50">Not configured</span>
                )}
              </div>
              {provider.api_key_set && (
                <button
                  onClick={() => toggleKey(provider.id)}
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-[var(--hm-surface-elevated)] hover:text-foreground"
                >
                  {revealedKeys.has(provider.id) ? (
                    <EyeOff className="h-3.5 w-3.5" />
                  ) : (
                    <Eye className="h-3.5 w-3.5" />
                  )}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
