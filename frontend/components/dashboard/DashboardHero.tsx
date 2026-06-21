// =============================================================================
// DashboardHero — "HiveMind Command Center" hero with gradient
// =============================================================================

export function DashboardHero() {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-gradient-to-br from-[var(--hm-primary)]/5 via-background to-background p-8">
      {/* Decorative gradient orb */}
      <div className="absolute -top-24 -right-24 h-64 w-64 rounded-full bg-[var(--hm-primary)]/10 blur-3xl" />
      <div className="absolute -bottom-16 -left-16 h-48 w-48 rounded-full bg-[var(--hm-primary)]/5 blur-3xl" />

      <div className="relative">
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="hm-gradient-text">HiveMind</span>{" "}
          <span className="text-foreground">Command Center</span>
        </h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-lg">
          Autonomous Multi-Agent Operating System — real-time observability for
          5 cooperating AI agents planning, researching, building, and reviewing
          deliverables end-to-end.
        </p>
      </div>
    </div>
  );
}
