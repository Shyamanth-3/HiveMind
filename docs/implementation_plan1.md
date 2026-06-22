# HiveMind — AI Operating System Frontend

Build the complete frontend for HiveMind: a real-time observability console for watching 5 autonomous AI agents (Queen, Architect, Scout, Builder, Guardian) plan, research, build, and review deliverables end-to-end.

## User Review Required

> [!IMPORTANT]
> **Recharts not installed** — `package.json` is missing `recharts`. I'll install it as the first step. The prompt specifies it for cost-by-agent and success-rate charts.

> [!IMPORTANT]
> **Dark-first theme override** — The existing `globals.css` has shadcn's default neutral theme with both light and dark variants. I'll replace the CSS variables with the HiveMind design tokens (Background `#09090B`, Surface `#111827`, Primary `#8B5CF6`, etc.) and force `dark` class on `<html>`. Light theme is explicitly out of scope for v1.

> [!IMPORTANT]
> **Tailwind CSS 4 + shadcn v4** — The project uses Tailwind v4 (CSS-first config, `@theme` blocks, no `tailwind.config.ts`) and shadcn v4 (`radix-nova` style). All theme customization goes in `globals.css`, not a JS config file.

## Proposed Changes

The build is organized into **8 phases**, ordered by dependency (foundation first, pages later).

---

### Phase 1 — Foundation Layer

Sets up types, agent mapping, theme tokens, and mock data. Everything else depends on this.

#### [NEW] [types/index.ts](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/types/index.ts)
TypeScript interfaces mirroring the backend data model exactly:
- `Project` — id, name, owner, created_at, goal_summary
- `Run` — id, project_id, goal, plan_text, status, success_criteria
- `Task` — id, run_id, type, assigned_agent (backend role key), depends_on[], status, result, retry_count
- `Event` — id, run_id, event_type (canonical strings), payload, cost_usd, latency_ms, created_at
- `MemoryChunk` — id, project_id, content, embedding metadata (source + dimensionality, never raw vector), source, created_at
- `AgentLog` — run_id, task_id, agent, prompt_tokens, completion_tokens, cost_usd, latency_ms, outcome, model
- `AgentStatus` — agent, status (online/idle/working), current_task, last_activity, tasks_completed, success_rate
- `SystemService` — name, status (online/offline/cold-start/degraded), latency_ms
- Union types for all status enums, `EventType`, `BackendRoleKey`, `AgentPersona`

#### [NEW] [lib/agentNames.ts](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/lib/agentNames.ts)
Single source of truth for the 5-agent mapping:
- `backendRoleToPersona` — `{ ceo_agent: "Queen", pm_agent: "Architect", research_agent: "Scout", developer_agent: "Builder", reviewer_qa_agent: "Guardian" }`
- `personaToBackendRole` — reverse mapping
- `getPersonaIcon(role)` — returns the Lucide icon component (Crown, Compass, Binoculars, Hammer, ShieldCheck)
- `getPersonaColor(role)` — returns a unique accent color per agent for charts/avatars
- `getPersonaDescription(role)` — one-line job description from the ground truth table

#### [MODIFY] [globals.css](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/globals.css)
Replace CSS variables with HiveMind design tokens. Map:
- `--background` → `#09090B`, `--foreground` → `#FAFAFA`
- `--card` / `--popover` → `#111827` (Surface)
- `--primary` → `#8B5CF6`
- `--destructive` → `#EF4444`
- `--muted-foreground` → `#A1A1AA`
- `--border` → `#27272A`
- Add custom properties: `--hm-surface-elevated: #18181B`, `--hm-success: #22C55E`, `--hm-warning: #F59E0B`
- Add `@keyframes` for pulse animation (agent "working" status), slide-in (event feed), flash-success, flash-danger
- Remove the light-mode `:root` block (dark-first only)

#### [MODIFY] [layout.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/layout.tsx)
- Add `dark` class to `<html>` element
- Update metadata: title "HiveMind — AI Operating System", description
- Use Inter font from `next/font/google` (premium typography)

#### [NEW] [lib/mockData.ts](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/lib/mockData.ts)
Realistic mock data using backend role keys (never persona names in data):
- 2 projects ("Local Bakery Marketing Site", "Dental Clinic Landing Page")
- 3 runs — one completed successfully, one running, one with a reject→retry cycle
- Tasks per run following the `goal_to_deliverable` shape with proper `depends_on[]`
- Events using canonical event types with realistic INR costs (₹5-8 per run) and latencies
- Memory chunks with source metadata and dimensionality (1536-dim)
- Agent status data (mix of online/idle/working)
- System service status (Postgres online, Redis online, LLM cold-start)

#### [NEW] [hooks/useEventStream.ts](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/hooks/useEventStream.ts)
Custom hook simulating a WebSocket event stream. Uses `setInterval` to drip-feed mock events. Shaped so replacing with a real WebSocket is a drop-in change (returns `{ events, isConnected, lastEvent }`).

---

### Phase 2 — Layout Shell

#### [NEW] [components/layout/Sidebar.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/layout/Sidebar.tsx)
280px persistent left sidebar:
- HiveMind logo (stylized text + icon, no external image)
- Nav items: Dashboard, Runs, Agents, Memory, Workflow, Research, Settings — each with Lucide icon, active state highlighting with primary color
- Bottom **System Status** block: PostgreSQL, Redis, LLM Provider — each with `SystemHealthCard` showing online/offline/cold-start with distinct indicators (green dot, red dot, amber pulsing dot for cold-start)

#### [NEW] [components/layout/TopNav.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/layout/TopNav.tsx)
Top bar with: breadcrumb for current page, global search (styled, non-functional stub), connection status indicator (WebSocket simulation)

#### [MODIFY] [components/layout/AppLayout.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/layout/AppLayout.tsx)
Client component composing Sidebar + TopNav + main content area. Handles sidebar collapse on smaller screens.

#### [MODIFY] [layout.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/layout.tsx)
Wrap children with `AppLayout`.

#### [NEW] [components/shared/StatusBadge.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/shared/StatusBadge.tsx)
Universal status badge using the defined color mapping:
- online/completed/approved → Success green
- idle/pending → Muted
- working/running → Primary purple with pulse animation
- rejected/failed → Danger red
- cold-start/degraded → Warning amber

#### [NEW] [components/shared/MetricCard.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/shared/MetricCard.tsx)
Glassmorphic card with icon, label, value, and optional trend indicator. Elevated surface background.

#### [NEW] [components/shared/PageHeader.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/shared/PageHeader.tsx)
Consistent page header with title, subtitle, and optional action buttons.

#### [NEW] [components/shared/SearchBar.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/shared/SearchBar.tsx)
Styled search input with icon, placeholder, glass effect.

#### [NEW] [components/layout/SystemHealthCard.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/layout/SystemHealthCard.tsx)
Compact card for sidebar system status — service name, status dot (with cold-start = pulsing amber), latency.

---

### Phase 3 — Dashboard (Command Center)

#### [MODIFY] [app/dashboard/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/dashboard/page.tsx)
Full dashboard page composing all widgets below.

#### [NEW] [components/dashboard/DashboardHero.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/DashboardHero.tsx)
"HiveMind Command Center" title + "Autonomous Multi-Agent Operating System" subtitle. Subtle gradient background.

#### [NEW] [components/dashboard/MetricsRow.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/MetricsRow.tsx)
5 `MetricCard`s: Active Runs, Agents Online, Task Success Rate (>80% target), Total Cost (₹), Memory Chunks Indexed.

#### [NEW] [components/dashboard/CostBreakdownChart.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/CostBreakdownChart.tsx)
Recharts bar chart — one bar per persona (Queen, Architect, Scout, Builder, Guardian), ₹ y-axis. Uses agent-specific colors. Labels use persona names resolved from role keys.

#### [NEW] [components/dashboard/RecentRunsTable.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/RecentRunsTable.tsx)
Table: Run ID (truncated), Goal, Status (StatusBadge), Created At, Duration. Clickable rows → link to `/runs`.

#### [NEW] [components/dashboard/EventFeed.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/EventFeed.tsx)
Live scrolling feed consuming `useEventStream`. Each entry: `[PersonaName] event_type · latency`. Slide-in animation for new entries. `task_rejected` flashes danger, `task_approved` flashes success. Shows canonical event types only.

#### [NEW] [components/dashboard/AgentHealthGrid.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/dashboard/AgentHealthGrid.tsx)
5 compact `AgentCard`s showing persona name, icon, status (Online/Idle/Working) with appropriate pulse.

---

### Phase 4 — Runs (Workflow Execution Monitoring)

#### [MODIFY] [app/runs/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/runs/page.tsx)
Runs list page with `RunTable` + filters.

#### [NEW] [components/runs/RunTable.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/runs/RunTable.tsx)
Full runs table with status chips, filters (status, project, date). Clicking a row opens `RunDetailDrawer`.

#### [NEW] [components/runs/RunDetailDrawer.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/runs/RunDetailDrawer.tsx)
Slide-in drawer containing:
- Goal + Queen's plan text + success criteria list
- `TaskGraphView` showing live status per node
- Execution timeline — chronological events with cost_usd (₹) and latency_ms
- **Retry indicator** — prominently surfaces reject→retry cycles

#### [NEW] [components/runs/TaskGraphView.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/runs/TaskGraphView.tsx)
**Reusable** across Runs + Workflow pages. Renders the exact `goal_to_deliverable` shape:
```
Queen → Architect → [Scout ‖ Builder] → Guardian → Store+Notify
                                    ↳ reject loops back to Builder
```
- Nodes use persona names (resolved from role keys) + icons
- Nodes colored by status (pending/running/completed/rejected)
- Edges drawn as SVG paths, including the reject→Builder back-edge
- Props: `tasks[]` for live instance (Runs) or `template` for static display (Workflow)

#### [NEW] [components/runs/ExecutionTimeline.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/runs/ExecutionTimeline.tsx)
Chronological event list for a single run, each row with persona icon, event type, cost (₹), latency.

---

### Phase 5 — Agents (Digital Workforce)

#### [MODIFY] [app/agents/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/agents/page.tsx)
Page with 5 `AgentCard`s + click-through to `AgentDetailPanel`.

#### [NEW] [components/agents/AgentCard.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/agents/AgentCard.tsx)
Card per agent: persona name, icon, one-line job description, Status (StatusBadge), Current Task, Last Activity, Tasks Completed, Success Rate. Takes `backendRoleKey` as prop, resolves everything via `lib/agentNames.ts`.

#### [NEW] [components/agents/AgentDetailPanel.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/agents/AgentDetailPanel.tsx)
Expanded view: INPUT→OUTPUT contract (e.g. Guardian: INPUT = completed task + success criteria, OUTPUT = task_approved or task_rejected + feedback). Recent activity log scoped to that agent.

---

### Phase 6 — Memory (Knowledge Base / RAG)

#### [MODIFY] [app/memory/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/memory/page.tsx)
Full memory page composing all memory components.

#### [NEW] [components/memory/MemorySearchBar.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/memory/MemorySearchBar.tsx)
"Search by meaning, not just keywords" — styled search with brain icon.

#### [NEW] [components/memory/MemoryChunkTable.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/memory/MemoryChunkTable.tsx)
Table: content (truncated 100 chars), project, source, created_at. Never shows raw embedding vectors.

#### [NEW] [components/memory/SimilaritySearchPanel.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/memory/SimilaritySearchPanel.tsx)
Input box + mocked top-k results with similarity scores (0.0–1.0), source reference.

#### [NEW] [components/memory/KnowledgeStats.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/memory/KnowledgeStats.tsx)
MetricCards: Total Chunks, Storage Used (vs 500MB free tier), Top Retrieved This Week.

#### [NEW] [components/memory/MemoryPipelineDiagram.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/memory/MemoryPipelineDiagram.tsx)
SVG diagram showing Write Path (agent output → chunk → embed → store in pgvector) and Read Path (new task → embed query → similarity search → top-k → inject into prompt). Callout: "Running on pgvector inside the primary Postgres instance — no separate vector database in v1."

---

### Phase 7 — Workflow + Research

#### [NEW] [app/workflow/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/workflow/page.tsx)
Workflow page: read-only YAML viewer + visual graph.

#### [NEW] [components/workflow/WorkflowYamlViewer.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/workflow/WorkflowYamlViewer.tsx)
Syntax-highlighted, read-only YAML display of the `goal_to_deliverable` workflow. Node IDs use backend role keys (`ceo_plan`, `pm_breakdown`, etc.) in the raw YAML.

#### [NEW] [components/workflow/WorkflowGraphView.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/workflow/WorkflowGraphView.tsx)
Reuses `TaskGraphView` in template mode (no live status, just the workflow shape). Disabled "Add Workflow" button with tooltip.

#### [NEW] [app/research/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/research/page.tsx)
Research page composing experiment components.

#### [NEW] [components/research/ExperimentComparisonTable.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/research/ExperimentComparisonTable.tsx)
ReAct vs. Reflection comparison: Task Success Rate, Cost per Task (₹), Avg Latency, Retry Rate. Clearly labeled as illustrative mock data.

#### [NEW] [components/research/ReasoningDiagram.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/research/ReasoningDiagram.tsx)
SVG diagram contrasting: ReAct (Thought → Action → Observation → repeat) vs. Reflection (Draft → Self-critique vs. criteria → Revise). Framed as Builder's internal loop.

#### [NEW] [components/research/FindingCard.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/research/FindingCard.tsx)
Callout card stating which strategy won on which metric.

---

### Phase 8 — Settings

#### [MODIFY] [app/settings/page.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/app/settings/page.tsx)
Full settings page with all sections.

#### [NEW] [components/settings/LLMProviderCards.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/settings/LLMProviderCards.tsx)
4 provider cards: Gemini ("Active · Free tier"), Claude, GPT, Ollama ("Local fallback"). Masked API key inputs.

#### [NEW] [components/settings/DatabaseSettings.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/settings/DatabaseSettings.tsx)
Supabase/Neon connection status. Note: pgvector on same instance.

#### [NEW] [components/settings/RedisSettings.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/settings/RedisSettings.tsx)
Upstash connection status with usage split (pub/sub, queues, cache).

#### [NEW] [components/settings/SystemSettings.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/settings/SystemSettings.tsx)
Retry cap for Guardian rejections, cost alert threshold (₹).

#### [NEW] [components/settings/ApiKeysSettings.tsx](file:///c:/Users/shyam/OneDrive/Desktop/HiveMind/frontend/components/settings/ApiKeysSettings.tsx)
Centralized masked key display. Note: secrets never committed to git.

---

## File Count Summary

| Category | New | Modified |
|---|---|---|
| Types / Lib / Hooks | 4 | 0 |
| Layout | 5 | 2 |
| Shared Components | 4 | 0 |
| Dashboard | 6 | 1 |
| Runs | 4 | 1 |
| Agents | 2 | 1 |
| Memory | 5 | 1 |
| Workflow + Research | 5 | 0 |
| Settings | 5 | 1 |
| **Total** | **~40 new** | **~7 modified** |

## Verification Plan

### Build Verification
```bash
cd frontend && npm run build
```
Must compile with zero TypeScript errors.

### Dev Server
```bash
cd frontend && npm run dev
```
Manually verify all 7 routes render correctly, sidebar navigation works, animations play, charts render.

### Key Verification Points
- All agent names resolve from backend role keys (never hardcoded persona strings in components)
- All costs display in ₹ (INR), realistic free-tier amounts
- Status badges use correct colors per the mapping
- Task graph renders the exact `goal_to_deliverable` shape with reject back-edge
- Event feed simulates WebSocket-style streaming
- At least one run shows a reject→retry cycle
- System health shows cold-start state (not just online/offline)
- Dark theme only, no light mode artifacts
