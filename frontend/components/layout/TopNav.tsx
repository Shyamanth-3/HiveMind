"use client";

import { cn } from "@/lib/utils";
import { usePathname } from "next/navigation";
import { Wifi, WifiOff } from "lucide-react";
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
      className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-border bg-background/80 backdrop-blur-md px-6"
      style={{ marginLeft: sidebarWidth }}
    >
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">HiveMind</span>
        <span className="text-muted-foreground/50">/</span>
        <span className="font-medium text-foreground">{pageTitle}</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search (stub) */}
      <SearchBar
        placeholder="Search anything..."
        className="w-64 hidden md:block"
      />

      {/* Connection Status */}
      <div
        className={cn(
          "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium",
          isConnected
            ? "bg-[var(--hm-success)]/10 text-[var(--hm-success)]"
            : "bg-[var(--hm-danger)]/10 text-[var(--hm-danger)]"
        )}
      >
        {isConnected ? (
          <Wifi className="h-3 w-3" />
        ) : (
          <WifiOff className="h-3 w-3" />
        )}
        <span>{isConnected ? "Connected" : "Disconnected"}</span>
      </div>
    </header>
  );
}
