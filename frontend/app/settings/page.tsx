"use client";

import { PageHeader } from "@/components/shared/PageHeader";
import { LLMProviderCards } from "@/components/settings/LLMProviderCards";
import { DatabaseSettings } from "@/components/settings/DatabaseSettings";
import { RedisSettings } from "@/components/settings/RedisSettings";
import { SystemSettings } from "@/components/settings/SystemSettings";
import { ApiKeysSettings } from "@/components/settings/ApiKeysSettings";
import { Palette } from "lucide-react";

// =============================================================================
// Settings Page
// =============================================================================

export default function SettingsPage() {
  return (
    <div className="space-y-8 max-w-[1200px] mx-auto">
      <PageHeader
        title="Settings"
        subtitle="Configure infrastructure connections, LLM providers, and system behavior."
      />

      <LLMProviderCards />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <DatabaseSettings />
        <RedisSettings />
      </div>

      <SystemSettings />

      <ApiKeysSettings />

      {/* Theme stub */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-4">Theme</h3>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-[var(--hm-primary)]/10 p-2">
              <Palette className="h-4 w-4 text-[var(--hm-primary)]" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Dark Mode</p>
              <p className="text-xs text-muted-foreground">
                Dark-first is the only supported theme in v1. Light mode is not
                available.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}