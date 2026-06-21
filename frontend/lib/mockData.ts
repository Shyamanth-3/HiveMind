// =============================================================================
// HiveMind — Mock Data
// Realistic data using backend role keys. Persona names are never in data —
// they're resolved at the presentation layer.
// Costs in INR (₹), reflecting real free-tier economics (₹5-8 per run).
// =============================================================================

import type {
  Project,
  Run,
  Task,
  Event,
  MemoryChunk,
  AgentStatusData,
  AgentLog,
  SystemService,
  LLMProvider,
} from "@/types";

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export const mockProjects: Project[] = [
  {
    id: "proj_01",
    name: "Bakery Marketing Site",
    owner: "shyam",
    created_at: "2026-06-20T10:00:00Z",
    goal_summary: "Create a 3-page marketing site for a local bakery",
  },
  {
    id: "proj_02",
    name: "Dental Clinic Landing",
    owner: "shyam",
    created_at: "2026-06-21T09:00:00Z",
    goal_summary: "Build a landing page for a dental clinic",
  },
];

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export const mockRuns: Run[] = [
  {
    id: "run_001",
    project_id: "proj_01",
    goal: "Create a 3-page marketing site for a local bakery with a menu, about page, and contact form",
    plan_text:
      "1. Research local bakery website best practices and competitor layouts.\n2. Design a responsive 3-page site: Home (hero + featured items), Menu (categorized item list with prices), Contact (form + map embed).\n3. Build with semantic HTML, modern CSS, and accessibility best practices.\n4. Review against success criteria and iterate if needed.",
    status: "completed",
    success_criteria: [
      "All 3 pages (Home, Menu, Contact) are functional and navigable",
      "Site is mobile-responsive across common breakpoints",
      "Contact form validates inputs before submission",
      "Page load time under 3 seconds on simulated 3G",
    ],
    created_at: "2026-06-20T10:05:00Z",
    duration_ms: 42300,
  },
  {
    id: "run_002",
    project_id: "proj_02",
    goal: "Build a landing page for a dental clinic with appointment booking CTA and services overview",
    plan_text:
      "1. Research dental clinic websites for conversion-optimized layouts.\n2. Design a single-page landing: Hero with CTA, Services grid, Testimonials carousel, Appointment booking section.\n3. Build with clean, professional design emphasizing trust signals.\n4. QA review against criteria.",
    status: "running",
    success_criteria: [
      "Landing page has a clear above-the-fold CTA for appointment booking",
      "Services section lists at least 6 dental services with icons",
      "Page includes at least 3 patient testimonials",
      "Design follows healthcare industry trust patterns",
    ],
    created_at: "2026-06-21T14:20:00Z",
    duration_ms: undefined,
  },
  {
    id: "run_003",
    project_id: "proj_01",
    goal: "Add an online ordering page to the bakery marketing site with cart functionality",
    plan_text:
      "1. Research e-commerce patterns for small bakery online ordering.\n2. Design an ordering page with category filters, item cards, and cart sidebar.\n3. Build interactive cart with add/remove/quantity controls.\n4. QA review — first attempt rejected for missing input validation, then approved after fix.",
    status: "completed",
    success_criteria: [
      "Ordering page displays categorized menu items with prices in ₹",
      "Cart updates in real-time with item count and total",
      "User can modify quantities and remove items",
      "Form validation prevents empty orders",
    ],
    created_at: "2026-06-21T08:00:00Z",
    duration_ms: 68400,
  },
];

// ---------------------------------------------------------------------------
// Tasks — following the goal_to_deliverable workflow shape
// Run 003 has a reject→retry cycle (Guardian rejects, Builder redoes)
// ---------------------------------------------------------------------------

export const mockTasks: Task[] = [
  // --- Run 001 (completed) ---
  { id: "task_001a", run_id: "run_001", type: "plan", assigned_agent: "ceo_agent", depends_on: [], status: "completed", result: "Plan created with 4 success criteria", retry_count: 0 },
  { id: "task_001b", run_id: "run_001", type: "breakdown", assigned_agent: "pm_agent", depends_on: ["task_001a"], status: "completed", result: "Task graph created with 4 tasks", retry_count: 0 },
  { id: "task_001c", run_id: "run_001", type: "research", assigned_agent: "research_agent", depends_on: ["task_001b"], status: "completed", result: "Found 12 bakery site references, wrote 5 memory chunks", retry_count: 0 },
  { id: "task_001d", run_id: "run_001", type: "build", assigned_agent: "developer_agent", depends_on: ["task_001b"], status: "completed", result: "3-page site built: index.html, menu.html, contact.html + styles.css", retry_count: 0 },
  { id: "task_001e", run_id: "run_001", type: "review", assigned_agent: "reviewer_qa_agent", depends_on: ["task_001c", "task_001d"], status: "approved", result: "All 4 success criteria met. Approved.", retry_count: 0 },

  // --- Run 002 (running) ---
  { id: "task_002a", run_id: "run_002", type: "plan", assigned_agent: "ceo_agent", depends_on: [], status: "completed", result: "Plan created with 4 success criteria", retry_count: 0 },
  { id: "task_002b", run_id: "run_002", type: "breakdown", assigned_agent: "pm_agent", depends_on: ["task_002a"], status: "completed", result: "Task graph created", retry_count: 0 },
  { id: "task_002c", run_id: "run_002", type: "research", assigned_agent: "research_agent", depends_on: ["task_002b"], status: "completed", result: "Researched 8 dental clinic sites", retry_count: 0 },
  { id: "task_002d", run_id: "run_002", type: "build", assigned_agent: "developer_agent", depends_on: ["task_002b"], status: "running", retry_count: 0 },
  { id: "task_002e", run_id: "run_002", type: "review", assigned_agent: "reviewer_qa_agent", depends_on: ["task_002c", "task_002d"], status: "pending", retry_count: 0 },

  // --- Run 003 (completed with reject→retry) ---
  { id: "task_003a", run_id: "run_003", type: "plan", assigned_agent: "ceo_agent", depends_on: [], status: "completed", result: "Plan created for ordering page", retry_count: 0 },
  { id: "task_003b", run_id: "run_003", type: "breakdown", assigned_agent: "pm_agent", depends_on: ["task_003a"], status: "completed", result: "Task graph created", retry_count: 0 },
  { id: "task_003c", run_id: "run_003", type: "research", assigned_agent: "research_agent", depends_on: ["task_003b"], status: "completed", result: "Found 6 e-commerce ordering patterns, recalled 2 memory chunks from prior bakery run", retry_count: 0 },
  { id: "task_003d", run_id: "run_003", type: "build", assigned_agent: "developer_agent", depends_on: ["task_003b"], status: "completed", result: "Ordering page built with cart (2nd attempt — added form validation)", retry_count: 1 },
  { id: "task_003e", run_id: "run_003", type: "review", assigned_agent: "reviewer_qa_agent", depends_on: ["task_003c", "task_003d"], status: "approved", result: "Approved on retry. Initial rejection: missing input validation on empty cart. Builder fixed and resubmitted.", retry_count: 0 },
];

// ---------------------------------------------------------------------------
// Events — canonical event types, realistic latencies and INR costs
// ---------------------------------------------------------------------------

export const mockEvents: Event[] = [
  // --- Run 001 events ---
  { id: "evt_001", run_id: "run_001", event_type: "run_created", agent: undefined, payload: { goal: "Create a 3-page marketing site for a local bakery" }, cost_usd: 0, latency_ms: 12, created_at: "2026-06-20T10:05:00Z" },
  { id: "evt_002", run_id: "run_001", event_type: "plan_ready", agent: "ceo_agent", payload: { criteria_count: 4 }, cost_usd: 0.008, latency_ms: 1240, created_at: "2026-06-20T10:05:02Z" },
  { id: "evt_003", run_id: "run_001", event_type: "tasks_created", agent: "pm_agent", payload: { task_count: 4 }, cost_usd: 0.006, latency_ms: 820, created_at: "2026-06-20T10:05:03Z" },
  { id: "evt_004", run_id: "run_001", event_type: "task_runnable", agent: "research_agent", payload: { task_id: "task_001c" }, cost_usd: 0, latency_ms: 5, created_at: "2026-06-20T10:05:03Z" },
  { id: "evt_005", run_id: "run_001", event_type: "task_runnable", agent: "developer_agent", payload: { task_id: "task_001d" }, cost_usd: 0, latency_ms: 5, created_at: "2026-06-20T10:05:03Z" },
  { id: "evt_006", run_id: "run_001", event_type: "task_completed", agent: "research_agent", payload: { chunks_written: 5 }, cost_usd: 0.012, latency_ms: 3200, created_at: "2026-06-20T10:05:08Z" },
  { id: "evt_007", run_id: "run_001", event_type: "task_completed", agent: "developer_agent", payload: { files_created: 4 }, cost_usd: 0.035, latency_ms: 8400, created_at: "2026-06-20T10:05:18Z" },
  { id: "evt_008", run_id: "run_001", event_type: "task_approved", agent: "reviewer_qa_agent", payload: { criteria_met: 4 }, cost_usd: 0.010, latency_ms: 1800, created_at: "2026-06-20T10:05:42Z" },
  { id: "evt_009", run_id: "run_001", event_type: "run_completed", agent: undefined, payload: { duration_ms: 42300 }, cost_usd: 0, latency_ms: 8, created_at: "2026-06-20T10:05:42Z" },

  // --- Run 003 events (with reject→retry) ---
  { id: "evt_010", run_id: "run_003", event_type: "run_created", agent: undefined, payload: { goal: "Add an online ordering page" }, cost_usd: 0, latency_ms: 10, created_at: "2026-06-21T08:00:00Z" },
  { id: "evt_011", run_id: "run_003", event_type: "plan_ready", agent: "ceo_agent", payload: { criteria_count: 4 }, cost_usd: 0.007, latency_ms: 1100, created_at: "2026-06-21T08:00:02Z" },
  { id: "evt_012", run_id: "run_003", event_type: "tasks_created", agent: "pm_agent", payload: { task_count: 4 }, cost_usd: 0.005, latency_ms: 750, created_at: "2026-06-21T08:00:03Z" },
  { id: "evt_013", run_id: "run_003", event_type: "task_completed", agent: "research_agent", payload: { chunks_written: 3, memory_recalled: 2 }, cost_usd: 0.011, latency_ms: 2800, created_at: "2026-06-21T08:00:08Z" },
  { id: "evt_014", run_id: "run_003", event_type: "task_completed", agent: "developer_agent", payload: { files_created: 2, attempt: 1 }, cost_usd: 0.032, latency_ms: 7600, created_at: "2026-06-21T08:00:20Z" },
  { id: "evt_015", run_id: "run_003", event_type: "task_rejected", agent: "reviewer_qa_agent", payload: { reason: "Missing input validation — empty cart can be submitted", criteria_failed: ["Form validation prevents empty orders"] }, cost_usd: 0.009, latency_ms: 1400, created_at: "2026-06-21T08:00:30Z" },
  { id: "evt_016", run_id: "run_003", event_type: "task_completed", agent: "developer_agent", payload: { files_modified: 1, attempt: 2, fix: "Added empty cart validation" }, cost_usd: 0.018, latency_ms: 4200, created_at: "2026-06-21T08:00:48Z" },
  { id: "evt_017", run_id: "run_003", event_type: "task_approved", agent: "reviewer_qa_agent", payload: { criteria_met: 4, note: "Approved after retry — validation fix verified" }, cost_usd: 0.008, latency_ms: 1200, created_at: "2026-06-21T08:01:00Z" },
  { id: "evt_018", run_id: "run_003", event_type: "run_completed", agent: undefined, payload: { duration_ms: 68400 }, cost_usd: 0, latency_ms: 6, created_at: "2026-06-21T08:01:08Z" },

  // --- Run 002 events (in progress) ---
  { id: "evt_019", run_id: "run_002", event_type: "run_created", agent: undefined, payload: { goal: "Build a landing page for a dental clinic" }, cost_usd: 0, latency_ms: 15, created_at: "2026-06-21T14:20:00Z" },
  { id: "evt_020", run_id: "run_002", event_type: "plan_ready", agent: "ceo_agent", payload: { criteria_count: 4 }, cost_usd: 0.009, latency_ms: 1350, created_at: "2026-06-21T14:20:02Z" },
  { id: "evt_021", run_id: "run_002", event_type: "tasks_created", agent: "pm_agent", payload: { task_count: 4 }, cost_usd: 0.006, latency_ms: 890, created_at: "2026-06-21T14:20:03Z" },
  { id: "evt_022", run_id: "run_002", event_type: "task_completed", agent: "research_agent", payload: { chunks_written: 4 }, cost_usd: 0.013, latency_ms: 3400, created_at: "2026-06-21T14:20:08Z" },
];

// ---------------------------------------------------------------------------
// Memory Chunks — with source and dimensionality, never raw vectors
// ---------------------------------------------------------------------------

export const mockMemoryChunks: MemoryChunk[] = [
  { id: "mem_001", project_id: "proj_01", content: "Local bakery websites typically feature high-quality food photography, warm color palettes (cream, brown, gold), and prominent menu sections. Mobile-first design is critical as 68% of bakery site visits are mobile.", embedding_dimensions: 1536, source: "web_search:bakery_website_best_practices", created_at: "2026-06-20T10:05:06Z" },
  { id: "mem_002", project_id: "proj_01", content: "Contact form best practices: include name, email, phone (optional), message fields. Use client-side validation for email format. Include a Google Maps embed for location.", embedding_dimensions: 1536, source: "web_search:contact_form_patterns", created_at: "2026-06-20T10:05:07Z" },
  { id: "mem_003", project_id: "proj_01", content: "Menu page layout: categorize items (Breads, Pastries, Cakes, Beverages). Each item needs name, description (1-2 lines), and price in local currency. Consider allergen badges.", embedding_dimensions: 1536, source: "web_search:bakery_menu_design", created_at: "2026-06-20T10:05:07Z" },
  { id: "mem_004", project_id: "proj_01", content: "E-commerce ordering patterns for small bakeries: simple cart sidebar, category filtering, item cards with photo/price/add button. Avoid complex checkout — keep it single-page.", embedding_dimensions: 1536, source: "web_search:bakery_ordering_patterns", created_at: "2026-06-21T08:00:06Z" },
  { id: "mem_005", project_id: "proj_01", content: "Form validation for ordering: validate quantity > 0, validate cart not empty before checkout, show inline error messages. Previous bakery run used similar patterns for contact form.", embedding_dimensions: 1536, source: "memory_recall:run_001", created_at: "2026-06-21T08:00:07Z" },
  { id: "mem_006", project_id: "proj_02", content: "Dental clinic websites prioritize trust signals: professional certifications, patient testimonials with photos, clean medical-grade color schemes (whites, blues, greens). Above-fold CTA for appointment booking is essential.", embedding_dimensions: 1536, source: "web_search:dental_clinic_web_design", created_at: "2026-06-21T14:20:06Z" },
  { id: "mem_007", project_id: "proj_02", content: "Common dental services to feature: General Dentistry, Cosmetic Dentistry, Orthodontics, Teeth Whitening, Dental Implants, Pediatric Dentistry. Use simple icons for each service.", embedding_dimensions: 1536, source: "web_search:dental_services_list", created_at: "2026-06-21T14:20:07Z" },
  { id: "mem_008", project_id: "proj_02", content: "Healthcare testimonials pattern: use patient first name + last initial, star rating, and brief quote. Include before/after photos where appropriate. Display in a carousel or grid.", embedding_dimensions: 1536, source: "web_search:healthcare_testimonials", created_at: "2026-06-21T14:20:07Z" },
];

// ---------------------------------------------------------------------------
// Agent Status — mix of online/idle/working
// ---------------------------------------------------------------------------

export const mockAgentStatus: AgentStatusData[] = [
  { agent: "ceo_agent", status: "idle", current_task: null, last_activity: "2026-06-21T14:20:02Z", tasks_completed: 3, success_rate: 100 },
  { agent: "pm_agent", status: "idle", current_task: null, last_activity: "2026-06-21T14:20:03Z", tasks_completed: 3, success_rate: 100 },
  { agent: "research_agent", status: "online", current_task: null, last_activity: "2026-06-21T14:20:08Z", tasks_completed: 3, success_rate: 100 },
  { agent: "developer_agent", status: "working", current_task: "Building dental clinic landing page", last_activity: "2026-06-21T14:22:00Z", tasks_completed: 3, success_rate: 87.5 },
  { agent: "reviewer_qa_agent", status: "idle", current_task: null, last_activity: "2026-06-21T08:01:00Z", tasks_completed: 3, success_rate: 100 },
];

// ---------------------------------------------------------------------------
// Agent Logs — observability data for cost/latency analysis
// ---------------------------------------------------------------------------

export const mockAgentLogs: AgentLog[] = [
  { run_id: "run_001", task_id: "task_001a", agent: "ceo_agent", prompt_tokens: 320, completion_tokens: 580, cost_usd: 0.008, latency_ms: 1240, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_001", task_id: "task_001b", agent: "pm_agent", prompt_tokens: 410, completion_tokens: 390, cost_usd: 0.006, latency_ms: 820, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_001", task_id: "task_001c", agent: "research_agent", prompt_tokens: 280, completion_tokens: 920, cost_usd: 0.012, latency_ms: 3200, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_001", task_id: "task_001d", agent: "developer_agent", prompt_tokens: 650, completion_tokens: 2800, cost_usd: 0.035, latency_ms: 8400, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_001", task_id: "task_001e", agent: "reviewer_qa_agent", prompt_tokens: 480, completion_tokens: 350, cost_usd: 0.010, latency_ms: 1800, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003a", agent: "ceo_agent", prompt_tokens: 300, completion_tokens: 520, cost_usd: 0.007, latency_ms: 1100, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003b", agent: "pm_agent", prompt_tokens: 380, completion_tokens: 340, cost_usd: 0.005, latency_ms: 750, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003c", agent: "research_agent", prompt_tokens: 260, completion_tokens: 780, cost_usd: 0.011, latency_ms: 2800, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003d", agent: "developer_agent", prompt_tokens: 580, completion_tokens: 2200, cost_usd: 0.032, latency_ms: 7600, outcome: "retried", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003d", agent: "developer_agent", prompt_tokens: 720, completion_tokens: 1400, cost_usd: 0.018, latency_ms: 4200, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003e", agent: "reviewer_qa_agent", prompt_tokens: 510, completion_tokens: 280, cost_usd: 0.009, latency_ms: 1400, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_003", task_id: "task_003e", agent: "reviewer_qa_agent", prompt_tokens: 490, completion_tokens: 260, cost_usd: 0.008, latency_ms: 1200, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_002", task_id: "task_002a", agent: "ceo_agent", prompt_tokens: 340, completion_tokens: 560, cost_usd: 0.009, latency_ms: 1350, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_002", task_id: "task_002b", agent: "pm_agent", prompt_tokens: 420, completion_tokens: 410, cost_usd: 0.006, latency_ms: 890, outcome: "success", model: "gemini-2.0-flash" },
  { run_id: "run_002", task_id: "task_002c", agent: "research_agent", prompt_tokens: 290, completion_tokens: 950, cost_usd: 0.013, latency_ms: 3400, outcome: "success", model: "gemini-2.0-flash" },
];

// ---------------------------------------------------------------------------
// System Services — includes cold-start state
// ---------------------------------------------------------------------------

export const mockSystemServices: SystemService[] = [
  { name: "PostgreSQL", status: "online", latency_ms: 24, details: "Supabase · pgvector enabled · 47MB / 500MB used" },
  { name: "Redis", status: "online", latency_ms: 8, details: "Upstash · pub/sub + queues + cache" },
  { name: "LLM Provider", status: "cold-start", latency_ms: 2400, details: "Gemini Flash · Free tier · Waking up after 15min idle" },
];

// ---------------------------------------------------------------------------
// LLM Providers (Settings)
// ---------------------------------------------------------------------------

export const mockLLMProviders: LLMProvider[] = [
  { id: "gemini", name: "Google Gemini", model: "gemini-2.0-flash", status: "active", tier: "Free tier", api_key_set: true, badge: "Active · Free tier" },
  { id: "claude", name: "Anthropic Claude", model: "claude-sonnet-4-20250514", status: "available", tier: "Pay-as-you-go", api_key_set: false },
  { id: "gpt", name: "OpenAI GPT", model: "gpt-4o-mini", status: "available", tier: "Pay-as-you-go", api_key_set: false },
  { id: "ollama", name: "Ollama (Local)", model: "llama3.2", status: "fallback", tier: "Self-hosted", api_key_set: true, badge: "Local fallback" },
];

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

/** Get all tasks for a specific run */
export function getTasksForRun(runId: string): Task[] {
  return mockTasks.filter((t) => t.run_id === runId);
}

/** Get all events for a specific run */
export function getEventsForRun(runId: string): Event[] {
  return mockEvents.filter((e) => e.run_id === runId);
}

/** Get total cost across all agent logs, in INR (×83 from USD) */
export function getTotalCostINR(): number {
  return mockAgentLogs.reduce((sum, log) => sum + log.cost_usd * 83, 0);
}

/** Get cost per agent role, in INR */
export function getCostByAgent(): Record<string, number> {
  const costs: Record<string, number> = {};
  for (const log of mockAgentLogs) {
    costs[log.agent] = (costs[log.agent] || 0) + log.cost_usd * 83;
  }
  return costs;
}

/** Get the event stream ordered for live feed (newest first) */
export function getRecentEvents(limit = 20): Event[] {
  return [...mockEvents]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, limit);
}
