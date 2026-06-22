"use client";

import { cn } from "@/lib/utils";
import { usePathname } from "next/navigation";
import { Wifi, WifiOff, Bell, Monitor } from "lucide-react";
import { SearchBar } from "@/components/shared/SearchBar";

// =============================================================================
// TopNav — Top bar with breadcrumb, search, connection status
// =============================================================================

interface TopNavProps {
  isConnected?: boolean;
  sidebarWidth: number;
}

const pageTitles: Record<string, string> = {
  "/dashboard": "Command Center",
  "/runs": "Workflow Execution",
  "/agents": "Digital Workforce",
  "/memory": "Knowledge Base",
  "/workflow": "Automation Engine",
  "/research": "Reasoning Experiments",
  "/settings": "Settings",
};

export function TopNav({ isConnected = true, sidebarWidth }: TopNavProps) {
  const pathname = usePathname();
  const pageTitle = pageTitles[pathname] || "HiveMind";

  return (
    <header
      className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-border bg-[var(--hm-surface)] px-6"
      style={{ marginLeft: sidebarWidth }}
    >
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[14px]">
        <span className="text-muted-foreground hover:text-[var(--hm-primary)] transition-colors cursor-pointer">Dashboard</span>
        <span className="text-muted-foreground/50">›</span>
        <span className="font-medium text-[var(--hm-primary)]">{pageTitle}</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <div className="relative hidden md:block w-[224px]">
        <SearchBar
          placeholder="Search..."
          className="w-full bg-[var(--hm-surface-elevated)] border-[#3a3a3a] h-9"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none flex items-center gap-1 text-[10px] text-muted-foreground bg-[var(--hm-surface)] px-1.5 py-0.5 rounded border border-border">
          <span>⌘</span>
          <span>K</span>
        </div>
      </div>

      {/* Icons */}
      <div className="flex items-center gap-2">
        <button className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--hm-surface-elevated)] text-muted-foreground hover:text-foreground transition-colors border border-border">
          <Monitor className="h-4 w-4" />
        </button>
        <button className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--hm-surface-elevated)] text-muted-foreground hover:text-foreground transition-colors border border-border">
          <Bell className="h-4 w-4" />
        </button>
      </div>

      {/* Connection Status */}
      <div
        className={cn(
          "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium border",
          isConnected
            ? "bg-[var(--hm-success)]/10 text-[var(--hm-success)] border-[var(--hm-success)]/20"
            : "bg-[var(--hm-danger)]/10 text-[var(--hm-danger)] border-[var(--hm-danger)]/20"
        )}
      >
        {isConnected ? (
          <Wifi className="h-3 w-3" />
        ) : (
          <WifiOff className="h-3 w-3" />
        )}
      </div>

      {/* Avatar */}
      <div className="h-9 w-9 rounded-full hm-gradient-border overflow-hidden p-[2px]">
        <div className="h-full w-full rounded-full bg-[var(--hm-surface-elevated)] flex items-center justify-center">
          <img src="/logo.png" alt="User Avatar" className="h-full w-full object-contain opacity-80" />
        </div>
      </div>
    </header>
  );
}
