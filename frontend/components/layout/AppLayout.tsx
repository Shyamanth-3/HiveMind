"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";

// =============================================================================
// AppLayout — Main layout composing Sidebar + TopNav + content area
// =============================================================================

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const sidebarWidth = isSidebarCollapsed ? 68 : 224;
  // The sign-in page is shown without the application chrome (there is no data to navigate before signing in).
  if (usePathname() === "/login") return <main className="min-h-screen p-6">{children}</main>;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />
      <div
        className="flex flex-1 flex-col transition-all duration-300"
        style={{ marginLeft: sidebarWidth }}
      >
        <TopNav sidebarWidth={0} />
        <main className="flex-1 p-6 overflow-y-auto hm-scrollbar">
          {children}
        </main>
      </div>
    </div>
  );
}
