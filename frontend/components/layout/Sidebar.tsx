"use client";

import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Play,
  Users,
  Brain,
  GitBranch,
  FlaskConical,
  Settings,
  Hexagon,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { SystemHealthCard } from "./SystemHealthCard";
import { mockSystemServices } from "@/lib/mockData";

// =============================================================================
// Sidebar — 280px persistent left sidebar with HiveMind nav and system status
// =============================================================================

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Runs", href: "/runs", icon: Play },
  { label: "Agents", href: "/agents", icon: Users },
  { label: "Memory", href: "/memory", icon: Brain },
  { label: "Workflow", href: "/workflow", icon: GitBranch },
  { label: "Research", href: "/research", icon: FlaskConical },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-[var(--sidebar)] transition-all duration-300",
        isCollapsed ? "w-[68px]" : "w-[280px]"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--hm-primary)]/10">
          <Hexagon className="h-5 w-5 text-[var(--hm-primary)]" />
        </div>
        {!isCollapsed && (
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-tight hm-gradient-text">
              HiveMind
            </span>
            <span className="text-[10px] text-muted-foreground">
              AI Operating System
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto hm-scrollbar">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                isActive
                  ? "bg-[var(--hm-primary)]/10 text-[var(--hm-primary)]"
                  : "text-muted-foreground hover:bg-[var(--hm-surface-elevated)] hover:text-foreground"
              )}
            >
              <item.icon
                className={cn(
                  "h-4.5 w-4.5 shrink-0",
                  isActive
                    ? "text-[var(--hm-primary)]"
                    : "text-muted-foreground"
                )}
              />
              {!isCollapsed && <span>{item.label}</span>}
              {isActive && !isCollapsed && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[var(--hm-primary)]" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* System Status */}
      <div className="border-t border-border p-3">
        {!isCollapsed && (
          <p className="mb-2 px-2.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            System Status
          </p>
        )}
        {!isCollapsed &&
          mockSystemServices.map((service) => (
            <SystemHealthCard key={service.name} service={service} />
          ))}
        {isCollapsed && (
          <div className="flex flex-col items-center gap-2">
            {mockSystemServices.map((service) => {
              const dotClass =
                service.status === "online"
                  ? "bg-[var(--hm-success)]"
                  : service.status === "cold-start"
                  ? "bg-[var(--hm-warning)] animate-hm-cold-pulse"
                  : "bg-muted-foreground";
              return (
                <span
                  key={service.name}
                  className={cn("h-2 w-2 rounded-full", dotClass)}
                  title={`${service.name}: ${service.status}`}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* Collapse Toggle */}
      <div className="border-t border-border p-3">
        <button
          onClick={onToggle}
          className="flex w-full items-center justify-center rounded-lg p-2 text-muted-foreground transition-colors hover:bg-[var(--hm-surface-elevated)] hover:text-foreground"
        >
          {isCollapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>
    </aside>
  );
}
