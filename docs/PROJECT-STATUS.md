# HiveMind — Project Status

Phase 0 baseline audit. Branch: `feature/5-multi-agent-system` (HEAD `7144e65`, large uncommitted working tree). Audit date: 2026-09-23.

Status legend: ✅ COMPLETE · 🟡 PARTIAL · 🔴 MISSING · ⚠️ BROKEN · 🔵 STALE DOCUMENTATION · ⚪ NOT VERIFIED

"Implemented" means the code exists and its call path was traced. "Verified" means it was executed. The Docker daemon was not running during this audit, so nothing that needs PostgreSQL, Kafka or a live LLM was executed. Those items are marked ⚪ where relevant.

---

## 1. Executive Summary

| Area | Status | One-line finding |
|---|---|---|
| Core architecture (event-driven, 5 agents) | 🟡 PARTIAL | Kafka-chained sequence of 5 agents exists in code; Scheduler/DAG/state machine from TDR-002 does not |
| FastAPI backend | 🟡 PARTIAL | Imports and registers 8 routers; several endpoints return mock/hardcoded data; one has a bug |
| Database | 🟡 PARTIAL | Models exist; migrations cannot build a fresh DB; the pipeline never writes to it |
| Kafka backbone | 🟡 PARTIAL | Producer/consumer/dispatch exist; no persistence, retry, idempotency, DLQ or failure events |
| Agents | 🟡 PARTIAL | All 5 run LlamaIndex workflows and emit validated structured output; Builder/Guardian operate on plans, not artifacts |
| Memory / RAG | 🟡 PARTIAL | pgvector store + search work by code trace; only Queen uses them; no other agent does |
| Frontend | 🟡 PARTIAL | Builds; most widgets call the real API; settings/agents/research have mock or hardcoded data |
| WebSockets / real-time | 🔴 MISSING | `useEventStream` is a client-side replay simulator; no WS/SSE exists anywhere |
| Guardian revision loop | 🔴 MISSING | Verdict field exists; nothing acts on it |
| Multi-provider LLM | 🔴 MISSING | Factory is hard-wired to Groq |
| Tests | ⚠️ BROKEN | 4/4 pytest tests error at setup; ad-hoc scripts are not tests; `test_queen.py` is stale |
| Docker / infra | 🟡 PARTIAL | Compose has only Postgres + Kafka; `backend/Dockerfile` and `.env.example` are 0 bytes |
| Documentation | 🔵 STALE DOCUMENTATION | README, TDR-001, TDR-002 and code comments still describe Redis and an older state |
| Security | ⚠️ BROKEN | A live API key sits in a git-tracked file (uncommitted); no auth |

The most important gap: **the pipeline does not persist anything to PostgreSQL.** Nothing writes `events`, `tasks`, `agent_logs`, or updates `runs.status`. The `/workflow/{id}/status` and `/outputs` endpoints read from the `events` table, so they return empty results for a real run.

---

## 2. Architecture

Intended (TDR-002): API → Scheduler → Redis Pub/Sub → agents → PostgreSQL + memory. Scheduler owns lifecycle, DAG readiness, retries, and failure handling.

Actual, traced from code:

```
POST /api/v1/runs
  run_service.create_run: insert Run row, publish KafkaEvent(run.created)     [app/services/run_service.py]
        |
        v  Kafka topic "hivemind.events" (single topic, key = run_id)
SchedulerConsumer (separate process: python -m app.scheduler)                  [app/scheduler/consumer.py]
  dict dispatch on event_type -> runs the next agent inline with asyncio.run()
  -> publishes the next event -> loop
```

- 🟡 Event-driven: agents never call each other. The Scheduler calls each agent service directly and republishes the result, which is compatible with the "agents don't talk directly" principle.
- 🔴 Scheduler responsibilities from TDR-002 that do not exist: run lifecycle state machine, Task DAG readiness evaluation, parallel execution, retry policy, failure handling.
- 🔴 No `run.failed`, `run.completed`, `task.ready`, or `revision.requested` events. `EventTypes` has 6 members (`app/events/event_types.py`).
- 🔵 Agent framework: TDR-001 says "Custom Agent Framework". Actual: **LlamaIndex Workflows** (`llama_index.core.workflow`) plus `llama-index-llms-groq`.
- 🔵 Message bus: TDR-001/002 say Redis Pub/Sub. Actual: Kafka (`confluent_kafka`), single topic.

---

## 3. Backend Status

Entry point `backend/app/main.py`: FastAPI app, lifespan creates a `KafkaEventBus` on `app.state`, CORS from settings, `/health` plus `/api/v1` router.

`python -c "import app.main"` and all five agent services and `app.scheduler.consumer` import cleanly in `backend/.venv`. ✅

| Router | Registered | Backed by | Status | Evidence |
|---|---|---|---|---|
| health (`/health/`) | yes | static | ✅ | Returns `{"Status":"Healthy"}` only; no dependency checks |
| projects | yes | DB | ⚪ | Service + API tests exist but tests error at setup (§11) |
| runs | yes | DB + Kafka | 🟡 | Create inserts and publishes `run.created`. Nothing ever updates status afterwards |
| tasks | yes | DB | 🟡 | CRUD only. No code creates Task rows during a run |
| events | yes | DB | 🟡 | Only `POST /events/` writes rows. The pipeline does not |
| memory (`/memory`) | yes | `memory_chunks` table | 🟡 | Reads/writes the non-vector legacy table. Does not touch `agent_memories` (§7) |
| agent-logs | yes | DB | 🟡 | Nothing writes `agent_logs` from agents |
| system | yes | mock | ⚠️ | `/system/agents` is a hardcoded list dated 2026-06-21. `/system/services`: Redis is hardcoded "online" though Redis is unused; LLM row is hardcoded "Gemini Flash"; latencies are constants. Postgres check calls `db.execute("SELECT 1")`, a raw string that SQLAlchemy 2.x rejects with `ObjectNotExecutableError`, which is caught and reported as `offline`. Inferred from source and the installed SQLAlchemy 2.0.51; not executed |
| workflow | yes | `events` table | 🟡 | Logic reads `event_service.get_events_by_run`; since no pipeline writer exists, output is empty for real runs |

Other backend findings:
- `Settings.REDIS_URL: str` has no default, so the app fails to start without a Redis URL even though Redis is not used (`app/core/config.py`). `redis` remains in `requirements.txt`.
- `backend/requirements.txt` (tracked) omits `llama-index*`, `llama-index-llms-groq`, and `psycopg-binary`, which the code needs. The `.venv` has them. An untracked root `requirements.txt` is a UTF-16 `pip freeze` and contains the LlamaIndex packages. `pip install -r backend/requirements.txt` would give a non-working environment.
- CORS is restricted to `settings.CORS_ORIGINS` (default `http://localhost:3000`) with `allow_credentials=True`. No wildcard origins. ✅
- No authentication on any endpoint (TDR-001 specifies JWT). 🔴

---

## 4. Database Status

Engine and session in `app/db/database.py` (psycopg3, `pool_pre_ping`). Alembic `env.py` imports `app.models`. ✅

| Table | Model | Migration | Written by app | Read by app | Notes |
|---|---|---|---|---|---|
| `projects` | ✅ | 🔴 | API + `seed.py` | API | |
| `runs` | ✅ | 🔴 | API create only | API, workflow | `status` default `"running"`; never transitions; `plan_text`, `success_criteria`, `duration_ms` never populated |
| `tasks` | ✅ | 🔴 | API only | API | Pipeline never creates rows. Builder's `TaskGraph` lives only in the Kafka payload |
| `events` | ✅ | 🔴 | `POST /events/` only | API, workflow | Not fed from Kafka |
| `agent_logs` | ✅ | 🔴 | nothing | API | `task_id` is a non-null FK to `tasks`, so logging LLM calls without a Task row is not possible as modelled |
| `memory_chunks` | ✅ | 🔴 | `POST /memory/` | API, frontend | No embedding column, only `embedding_dimensions` int |
| `agent_memories` | ✅ | ✅ (`ec1377b20fa7`) | Queen only | Queen only | `Vector(4096)` |
| `artifacts` | 🔴 | 🔴 | n/a | n/a | Documented in TDR-002; does not exist in code |
| `agent_executions` | 🔴 | 🔴 | n/a | n/a | Documented; does not exist |

- ⚠️ The initial Alembic migration `31ac285a6970` is empty (`pass`). The only real migration creates `agent_memories` with an FK to `runs.id`. On a fresh database `alembic upgrade head` would fail on that FK because `runs` does not exist. The schema is actually built by `Base.metadata.create_all` (via `create_tables.py` or `seed.py`). Not executed (no DB).
- ⚠️ `create_tables.py` runs `Base.metadata.drop_all()` before `create_all()`. Running it destroys all data. It is listed in `backend/.gitignore`.
- ⚠️ `create_run.py` inserts a `Run` without the non-null `project_id`, so it would fail.
- `agent_memories.embedding` is `Vector(4096)` with no ANN index. pgvector's HNSW and IVFFlat indexes cap at 2000 dimensions for `vector`, so search is an exact scan. Fine at small scale; not scalable.
- `app/memory/models` file `agent_memory.py` defines `class MemoryType(str, Enum)` where `Enum` is imported from `sqlalchemy` (a column type), not `enum`. It is not referenced anywhere else in the code I searched. Dead and misleading.
- IDs are strings (`String(36)`), not UUID columns. Timestamps are timezone-aware. ✅

---

## 5. Kafka/Event Backbone Status

Files: `app/events/{event_bus,kafka_event_bus,schemas,event_types}.py`, `app/scheduler/{consumer,__main__}.py`.

- Config: `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`, one topic `hivemind.events`, group `hivemind-scheduler`.
- ✅ Producer: `KafkaEventBus.publish` sets `enable.idempotence=True`, keys by `run_id`, so per-run ordering is preserved on one partition.
- ✅ Envelope: `KafkaEvent {event_id, event_type, source, timestamp, run_id, payload}`. Differs from TDR-002 (`source_agent` → `source`). 🔵
- 🟡 Consumer: manual poll loop, `enable.auto.commit=True`, `auto.offset.reset=earliest`, SIGINT/SIGTERM handling.

Transition table (traced from `consumer.py`):

| # | Event consumed | Producer of that event | Handler | Agent invoked | DB update | Next event published |
|---|---|---|---|---|---|---|
| 1 | `run.created` | `run_service.create_run` | `_handle_run_created` | Queen | none | `strategy.created` |
| 2 | `strategy.created` | Scheduler (as `queen_agent`) | `_handle_strategy_created` | Architect | none | `architecture.created` |
| 3 | `architecture.created` | Scheduler (as `pm_agent`) | `_handle_architecture_created` | Scout | none | `research.completed` |
| 4 | `research.completed` | Scheduler (as `research_agent`) | `_handle_research_completed` | Builder | none | `tasks.generated` |
| 5 | `tasks.generated` | Scheduler (as `developer_agent`) | `_handle_tasks_generated` | Guardian | none | `review.completed` |
| 6 | `review.completed` | Scheduler (as `reviewer_qa_agent`) | **no handler** | none | none | none. Pipeline stops here; `run.completed` never emitted, `runs.status` never updated |

Mismatches versus TDR-002's lifecycle:
- 🔴 States CREATED / PLANNING / DECOMPOSITION / RESEARCH / EXECUTION / REVIEW / COMPLETED / FAILED / CANCELLED are not implemented anywhere; there is no column or code for them.
- 🔴 Topics `goal.submitted`, `task.ready`, `build.completed`, `revision.requested`, `run.completed`, `run.failed` do not exist. Names in use differ (`run.created`, `architecture.created`, `tasks.generated`, `review.completed`).
- The `source` labels in published events use legacy role keys (`pm_agent`, `developer_agent`, `reviewer_qa_agent`), not `architect`/`builder`/`guardian`.

Reliability:
- 🔴 Failures: `_dispatch` catches every exception, logs it, and moves on. Offsets are auto-committed, so a failed step is silently dropped. No `run.failed` event, no dead-letter topic, no run status change. The run hangs forever.
- 🔴 Retry: none at the Scheduler level. Only LLM structured-output retry inside agents (`with_retry`, 2 attempts).
- 🔴 Idempotency: none. `event_id` is never checked. Delivery is at-least-once with auto-commit; a crash mid-handler or consumer rebalance can lose or replay a step, re-running LLM calls and re-emitting downstream events.
- 🟡 Each handler calls `asyncio.run(...)` inside the blocking poll loop. A long LLM chain can exceed `max.poll.interval.ms` (default 5 min) and trigger a rebalance. Not measured. ⚪
- 🔴 Persistence: no code path persists consumed events to `events`.
- Producer failures: `publish` re-raises only on immediate exceptions; delivery errors are only logged in the callback. `flush` occurs only in `close()` in the API. The Scheduler's own producer is never flushed or closed on shutdown. 🟡
- ⚪ Never executed. Kafka not running.

---

## 6. Agent Status

Common structure: each agent has `service.py`, `workflow.py` (LlamaIndex Workflow with receive → analyze → generate → validate steps), `prompts.py`, `schemas.py`, `events.py`, `exceptions.py`. Shared code in `agents/base/` (`with_retry`, validation helpers, exceptions). All run through `get_llm()`, which returns Groq (`llama-3.3-70b-versatile` from settings) for every agent. Every agent imports cleanly. ✅

Cross-cutting findings:
- 🟡 Each workflow's "analyze" step makes an extra LLM call whose output is stored in the workflow context (`ctx.store.set(...)`) and **never used by the next step's prompt** (checked in Architect, Scout, Builder, Guardian `generate_*` steps, whose prompts receive only structured inputs). This doubles LLM calls for no effect.
- 🟡 `agent_name` passed to `get_llm(...)` is ignored (`get_llm` always returns `GroqLLM().llm`).
- 🔴 No agent writes `agent_logs`, `tasks`, or `events`.
- 🟡 The Queen validates that phase IDs are sequential, count is in range, and so on. Other agents have their own validators. Validation failures raise, and the Scheduler drops them (§5).

### Queen
- Inputs: `run_id`, `goal` (payload of `run.created`).
- Processing: retrieve memory, LLM `GoalAnalysis`, LLM `LLMStrategy` (with memory context), validate, store strategy into memory.
- LLM: Groq via `get_llm()`.
- Outputs: `Strategy {summary, phases[]}`.
- Consumes `run.created`; the Scheduler publishes `strategy.created` on its behalf.
- DB: writes `agent_memories` only.
- Memory: reads (`memory_service.search(db, query=goal, limit=3)` in `receive_goal`) and writes (`memory_service.store` in `validate_strategy`). Both wrapped in try/except that only logs a warning, so failures degrade silently.
- Error handling: `with_retry` (2 attempts), validation.
- Status: 🟡 PARTIAL. Works by code trace and is the only memory-integrated agent. Success criteria (mentioned in TDR/Run model) are not produced. ⚪ not executed.

### Architect
- Inputs: goal + `Strategy`. Outputs: `ArchitecturePlan` (components, dependencies, execution_order, milestones, risk_assessment).
- Validates unique component IDs and that dependencies and milestones reference real components.
- Does **not** generate a task DAG; that is done by Builder. This deviates from TDR-002, where the Architect owns DAG generation.
- Memory: none. DB: none.
- Status: 🟡 PARTIAL. Structurally sound; cycle detection on component dependencies not present.

### Scout
- Inputs: goal + `ArchitecturePlan`. Outputs: `ResearchReport` (findings, library recommendations, security/performance considerations).
- ⚠️ Research is purely LLM-generated. `ScoutService` contains a comment placeholder listing `search_web/search_github/search_docs/search_vector_db`, none implemented. Tavily (TDR-001) is not integrated. The findings are model recall, not retrieved sources.
- Memory: none. DB: none.
- Status: 🟡 PARTIAL.

### Builder
- Inputs: goal + plan + research. Output: `TaskGraph` (list of tasks with dependencies, `assigned_agent` restricted to `developer_agent`).
- Validation checks dependencies point to earlier task IDs (which also guarantees acyclicity).
- ⚠️ Builder does **not** build deliverables. It produces a task list. No artifacts (files, code, copy) are generated, and there is no storage layer. TDR-002's "Builder generates artifacts" is unimplemented.
- Memory: none. DB: none (`tasks` table unused).
- Status: 🟡 PARTIAL. Named Builder but behaves as a second planner.

### Guardian
- Inputs: plan + research + task graph. Output: `ValidationReport` with `overall_verdict ∈ {approved, needs_revision, rejected}` and review sections.
- It reviews plan summaries only (prompt receives `architecture_summary`, `research_summary`, `task_graph_summary`), not deliverables or full content.
- Verdict is published in `review.completed` and then ignored (see "Guardian revision loop" below).
- Memory: none. DB: none.
- Status: 🟡 PARTIAL.

Dead code: `agents/queen/agent_old.py` and the `BaseLLM` interface (`agents/llm/base.py`), and `agents/llm/schemas.py` (misspelled `Stratergy`), are not referenced by any active code path. Details in §14.

### Guardian revision loop

Classification: 🔴 MISSING (only the data field exists).

Evidence (searched `backend/app` and `backend/agents`):
- Guardian schema/prompt/validation reference `needs_revision` (`agents/guardian/schemas.py`, `prompts.py`, `workflow.py`).
- `app/` contains zero references to "revision". No `revision.requested` event type. `EventTypes` lacks it.
- `SchedulerConsumer` has no handler for `review.completed`, so a `needs_revision` or `rejected` verdict changes nothing.
- Builder accepts no revision feedback input; no `revision_count`/max-revision counter exists; there is no loop, so no infinite-loop risk exists today, and none is guarded against.

---

## 7. Memory / RAG Status

Code: `app/memory/{embeddings,service,schemas,exceptions}.py`, `app/models/agent_memory.py`, migration `ec1377b20fa7`.

| Layer | Status | Evidence |
|---|---|---|
| A. Memory storage | 🟡 PARTIAL | `MemoryService.store` inserts `AgentMemory` rows (`agent_memories`). Only caller: `QueenWorkflow.validate_strategy` stores one memory per run (goal + strategy summary). Artifacts, research and reviews are never stored. |
| B. Embedding generation | 🟡 PARTIAL | `FeatherlessEmbeddingProvider` (OpenAI-compatible client, model `Qwen/Qwen3-Embedding-8B`). Single provider. Needs `FEATHERLESS_API_KEY`; if unset it logs a warning and calls with a dummy key. Calls are synchronous and run inside async workflow steps, blocking the event loop. Dimension is hardcoded 4096 in `get_dimension()`, with an adjacent comment claiming 3584. Actual model dimension is ⚪ not verified. |
| C. Vector persistence | ✅ COMPLETE (code) | `Vector(4096)` column, `CREATE EXTENSION IF NOT EXISTS vector` in migration, compose uses `pgvector/pgvector:pg17`. ⚪ not run against a live DB. No ANN index. |
| D. Semantic retrieval | ✅ COMPLETE (code) | `MemoryService.search` uses `AgentMemory.embedding.cosine_distance(...)`, ordered ascending, `similarity = 1 - distance`, limit param. ⚪ not run. |
| E. Filtering | 🟡 PARTIAL | `agent`, `memory_type`, `run_id` filters implemented in `search`. No `project_id` filter (column absent). Queen calls it with no filters, so retrieval is global across all runs and projects. |
| F. Context construction | 🟡 PARTIAL | Queen numbers retrieved memories into a string and passes them as `memory_context` to `QUEEN_STRATEGY_PROMPT`. No ranking, similarity threshold, deduplication, or token budget. |
| G. Agent integration | 🟡 PARTIAL | Only Queen. Repo-wide search for `MemoryService`/`.search(`/`.store(` shows usage in `agents/queen/{service,workflow}.py` only. Architect, Scout, Builder, Guardian never read or write memory. |
| **End-to-end RAG** | 🟡 PARTIAL | A write, retrieve, prompt-augment loop exists for one agent (Queen), and only benefits later runs. Not verified by execution. |

Additional findings:
- ⚠️ Two unrelated memory systems coexist. `/api/v1/memory` and the whole Memory frontend page read `memory_chunks` (no vectors, seeded/mock content). The agents write to `agent_memories`. There is no API to query, search, or list `agent_memories`, so the UI cannot show real agent memory.
- 🔵 TDR-002 describes one `memory_chunks` table with `source_artifact_id`, `chunk_text`, `embedding`, plus chunking. No chunking exists (each memory is one embedded text blob). The actual table names, columns, and structure differ.
- Failure handling: retrieval and store errors are swallowed with `logger.warning`. If the embedding key is missing, Queen silently proceeds with no memory.

---

## 8. Frontend Status

Next.js **16.2.9** and React 19.2.4 (`package.json`), not Next 15 as in TDR-001. 🔵 `frontend/AGENTS.md` warns of breaking changes in this version.

Static validation:
- `npm run build`: ✅ compiles, TypeScript passes, 11 static pages generated. Non-fatal warning: Recharts "width(-1) and height(-1)" during prerender.
- `npm run lint`: ⚠️ 26 problems (11 errors, 15 warnings). Examples: `react-hooks/set-state-in-effect` in `use-mobile.ts`; `react-hooks/use-memo` in `useApi.ts` (non-literal deps array); `no-explicit-any` in `lib/api.ts` (`fetchWorkflowStatus`/`fetchWorkflowOutputs`) and `types/index.ts`.

Pages (all client-rendered, statically prerendered):

| Route | Data source | Loading/error UI | Status |
|---|---|---|---|
| `/` | redirects to `/dashboard` | n/a | ✅ |
| `/dashboard` | Widgets call the API via `useApi` (`MetricsRow`, `RecentRunsTable`, `CostBreakdownChart`, `AgentHealthGrid`) plus the simulated `EventFeed` | `useApi` returns loading/error; page-level handling minimal | 🟡 |
| `/runs` | `RunTable`, `RunDetailDrawer` via API | partial | 🟡 |
| `/workflow` | `WorkflowGraphView`, `WorkflowYamlViewer`. Neither imports `@/lib/api` and neither uses `useApi` (grep). The `/workflow/{id}/status` and `/outputs` client functions in `lib/api.ts` have no callers found in components | none | 🟡 static/⚪ |
| `/agents` | `useApi(fetchAgentStatuses)` → backend `/system/agents`, which is **mock data** | partial | ⚠️ mock end-to-end |
| `/research` | `ExperimentComparisonTable` has a hardcoded `comparisonData` array; `FindingCard`, `ReasoningDiagram` are static | none | 🟡 static |
| `/memory` | `KnowledgeStats`, `MemoryChunkTable` via API → legacy `memory_chunks` (no vectors). `SimilaritySearchPanel`/`MemorySearchBar` do not call any backend search endpoint (none exists) | partial | 🟡 |
| `/settings` | `LLMProviderCards` imports `mockLLMProviders` from `lib/mockData.ts`; `ApiKeysSettings` hardcoded; `RedisSettings` has hardcoded `usageSplit` and shows Redis, which is not used | none | ⚠️ mock |

- `lib/mockData.ts` (261 lines) is imported by one component only (`LLMProviderCards.tsx`). `app/dashboard/data.json` and several shadcn dashboard-template components (`section-cards`, `data-table`, `chart-area-interactive`, `nav-*`, `site-header`, `app-sidebar`) appear to be unused scaffold leftovers (⚪ needs verification, see §14).
- API base URL is hardcoded to `http://localhost:8000/api/v1` in `lib/api.ts` (no env var).
- No frontend path exists to submit a goal or create a run. The only run creation paths found are the REST API and the scripts. (⚪ verify that no form exists; grep for `POST` in `lib/api.ts` shows none, since the client is GET-only.)
- There is no run-detail page that shows agent outputs (strategy, plan, research, task graph, review).

---

## 9. WebSocket Status

Classification: 🔴 MISSING (real-time transport). The UI has a simulation.

Trace: backend event → transport → frontend hook → UI.
- Backend: no `WebSocket` or `EventSource`/SSE route anywhere in `backend/app`. Kafka events do not reach the browser.
- Transport: none. The hook header claims "WebSocket Event Stream (API-backed)".
- `hooks/useEventStream.ts`: fetches `GET /events/recent?limit=50` once (after an 800 ms `setTimeout`), then a `setInterval` (3–6 s) **replays those old events in a loop** with fresh client-side timestamps and modified IDs (`${event.id}_${Date.now()}`). The dashboard `EventFeed` therefore shows historical events presented as live. ⚠️ Misleading to a user.
- If the fetch fails, it sets `isConnected=true` with an empty list (no error state).
- No polling of run status either. `TanStack Query` (TDR-001) is not a dependency in `frontend/package.json`.

---

## 10. LLM Provider Status

- 🟡 PARTIAL: LlamaIndex `LLM` abstraction is in use (`get_llm() -> LLM`), so provider swap is one function away. This is an accidental abstraction.
- ✅ Groq: `agents/llm/groq_client.py` wraps `llama_index.llms.groq.Groq` using `LLM_MODEL` and `GROQ_API_KEY`.
- 🔴 OpenAI, Anthropic, Gemini, Ollama: no implementations. `get_llm` ignores `LLM_PROVIDER` and `agent_name`; code after the `return` (`raise ValueError("Unsupported provider")`) is unreachable.
- 🟡 Embeddings use a separate provider abstraction (`BaseEmbeddingProvider` + factory) with only Featherless implemented.
- Dead: `agents/llm/base.py::BaseLLM` (custom interface) is used only by `agent_old.py`.
- 🔵 `system_service` reports "Gemini Flash". `AgentLog.model` comment says `gemini-2.0-flash`. `test_llm.py` calls Groq through the OpenAI SDK directly.
- `opencode.json` (untracked) configures a different tool (Featherless/Qwen). It is not part of the app.
- `GROQ_API_KEY: str` is required with no default, so the app cannot start without it. Nothing else needs it at import time.

---

## 11. Testing Status

Executed: `backend/.venv/Scripts/python -m pytest tests -q` → **4 errors, 0 passed**.

- ⚠️ All 4 tests (`tests/api/test_projects.py` ×2, `tests/api/test_runs.py` ×2) fail at fixture setup: `CompileError: (in table 'agent_memories', column 'metadata_'): Compiler SQLiteTypeCompiler can't render element of type JSONB`. `conftest.py` builds all `Base.metadata` on in-memory SQLite, but `AgentMemory` uses `JSONB` and pgvector `Vector`, neither of which SQLite supports. The suite broke when `agent_memories` was added. The failing tests did not modify their own logic; not changed.
- `conftest.py` also does not override the event bus dependency. `create_run` needs `app.state.event_bus`, which is only set in the lifespan. `TestClient(app)` without a context manager does not run lifespan, so `test_runs` would fail at `get_event_bus` even after the SQLite fix. Inferred by reading, not executed. ⚪
- Root-level scripts are not tests. They are manual, live-service scripts:

| Script | Type | Requires | State |
|---|---|---|---|
| `test_queen.py` | manual | LLM key | ⚠️ BROKEN: `QueenWorkflow(llm=get_llm())` omits the required `memory_service` argument (`QueenWorkflow.__init__(self, llm, memory_service, **kwargs)`), so it raises `TypeError`. Stale relative to the memory change |
| `test_architect.py`, `test_scout.py`, `test_builder.py`, `test_guardian.py` | manual, one agent with hand-built inputs | LLM key | ⚪ not executed (would spend LLM credits); imports OK |
| `test_pipeline.py` | manual, chains 5 services in-process, bypassing Kafka | LLM key + DB + embedding key | ⚪ not executed |
| `test_e2e.py` | manual, HTTP against `127.0.0.1:8000` | running API, DB, Kafka, Scheduler | ⚪ not executed |
| `test_llm.py`, `test_db.py` | connectivity smoke scripts | key / DB | ⚪ not executed |

Pytest collects `test_*.py` in the backend root too, so a bare `pytest` will also execute these network scripts at import or collection time. No `pytest.ini`/`pyproject` scopes it to `tests/`.
- Coverage gaps versus TDR-001 (agents, events, APIs, memory, workflows): no tests for agents, Kafka, scheduler, memory service, or workflow API. `pytest-asyncio` is not in `backend/requirements.txt`.
- No frontend tests. No CI configuration found (no `.github/workflows`).
- ruff and mypy are not installed or configured. No backend lint or type checking was run.

---

## 12. Docker / Infrastructure Status

`docker-compose.yml` (has obsolete `version: "3.9"`):
- ✅ `postgres`: `pgvector/pgvector:pg17`, port 5432, named volume. No healthcheck.
- ✅ `kafka`: `apache/kafka:latest` (unpinned) in KRaft mode (no Zookeeper), port 9092, advertised `localhost:9092`, named volume. No healthcheck. No topic creation (relies on broker auto-create default).
- 🔴 No `backend`, `scheduler`, or `frontend` services, though TDR-001 says `docker-compose up` starts Next.js, FastAPI, PostgreSQL, and Redis.
- 🔴 `backend/Dockerfile` is **0 bytes**.
- 🔴 `.env.example` is **0 bytes**, so required settings are undocumented (`DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY`, `FEATHERLESS_API_KEY`, Kafka vars).
- 🔴 `infrastructure/` referenced in README does not exist. `docs/infrastructure/` is empty (`.gitkeep`).
- 🟡 Postgres credentials in compose are the literal `password` (dev default; `backend/.env` matches).
- Startup path from scratch, as it would have to work today: `docker compose up -d` → create Python env (requirements incomplete) → create `.env` by hand → `python create_tables.py` (drops tables) or `seed.py` (Alembic cannot build the schema) → `uvicorn app.main:app` → `python -m app.scheduler` in a second terminal → `npm run dev`. ⚪ not executed; Docker Desktop's engine was not running.

---

## 13. Documentation Status

🔵 STALE DOCUMENTATION items:

| Location | Statement | Reality |
|---|---|---|
| `README.md` | Backend Foundation / Redis Event Bus / Agent Framework "In Progress"; Agent Orchestration "Planned" | Backend, Kafka, five agents, memory are implemented (partially) |
| `README.md` | Stack lists Redis Pub/Sub; "All communication occurs through Redis events" | Kafka |
| `README.md` | Project structure shows `infrastructure/` and `TDR-001-HiveMind-Tech-Stack.md` at root | Neither exists; TDR is in `docs/decisions/` |
| `README.md` | Frontend "Next.js" | Next 16 |
| TDR-001 | Redis Pub/Sub, "Future upgrade Redis → Kafka" | Upgrade has already happened, undocumented (no TDR for it) |
| TDR-001 | Custom Agent Framework | LlamaIndex Workflows |
| TDR-001 | OpenAI/Anthropic/Gemini/Ollama | Groq only |
| TDR-001 | TanStack Query, Loguru, JWT, WebSockets, Tavily | None present (stdlib `logging`, no auth, no WS, no Tavily) |
| TDR-001 | Next.js 15 | 16.2.9 |
| TDR-002 | Redis Pub/Sub topics, `source_agent`, `goal.submitted`, etc. | Kafka, different names (§5) |
| TDR-002 | Tables `artifacts`, `agent_executions`, `memory_chunks(embedding)` | Absent / different (§4, §7) |
| TDR-002 | Scheduler owns lifecycle, DAG, retries | Not implemented (§2, §5) |
| TDR-002 | Architect generates DAG; Builder generates artifacts | Builder generates the task graph; no artifacts |
| Code comments/docstrings | `app/models/event.py` ("Redis pub/sub"), `system_service.py` (Redis, Gemini), `AgentLog.model` (Gemini), `Task` comments (`ceo_agent`, `pm_agent`) | Stale naming |
| `docs/specs/`, `docs/infrastructure/` | Empty `.gitkeep` | No specs written |
| Diagram `System_Architecture.png` | Not opened as an image; the doc text says Redis | ⚪ likely shows Redis |

No ADR exists for: Kafka adoption, LlamaIndex adoption, Groq as provider, Featherless/Qwen embeddings, `agent_memories` design.

---

## 14. Dead Code / Cleanup

Not deleted. Classifications only.

| File / item | Class | Evidence |
|---|---|---|
| `backend/agents/queen/agent_old.py` | SAFE TO DELETE | Untracked; imports `agents.llm.base.BaseLLM`; not imported by anything (`git status` shows `agent.py` deleted, and this file is its renamed copy) |
| `backend/agents/llm/base.py` (`BaseLLM`) | SAFE TO DELETE (once `agent_old.py` goes) | Only referenced by `agent_old.py` |
| `backend/agents/llm/schemas.py` (`Stratergy`, `StratergyPhase`) | NEEDS VERIFICATION | No importers found under `agents/`; superseded by `agents/queen/schemas.py` |
| `backend/app/__pycache__/main.cpython-313.pyc` | SAFE TO DELETE | Tracked compiled file (`git ls-files` shows 1 tracked pyc); should be `git rm --cached` |
| `backend/create_tables.py` | NEEDS VERIFICATION | Destructive `drop_all`; the only current schema-creation path, so it is functionally required until Alembic is fixed |
| `backend/create_run.py` | SAFE TO DELETE | Broken (missing `project_id`); lists a legacy status |
| `backend/test_db.py`, `test_llm.py` | NEEDS VERIFICATION | Connectivity smoke scripts; not tests |
| `backend/test_queen.py` | NEEDS VERIFICATION | Broken; tracked |
| `backend/test_architect/scout/builder/guardian/pipeline/e2e.py` | NEEDS VERIFICATION | Useful manual harnesses in the wrong place; belong under `scripts/` |
| `backend/seed.py` | ACTIVE | Loads mock data the frontend depends on |
| `app/api/health.py` | ACTIVE | |
| `app/models/agent_memory.py::MemoryType` | NEEDS VERIFICATION | Wrong `Enum` import, unreferenced |
| `redis` in `backend/requirements.txt`; `Settings.REDIS_URL`; Redis card in `system_service` and `RedisSettings.tsx` | NEEDS VERIFICATION | No code path uses Redis |
| Root `requirements.txt` (UTF-16 pip freeze, untracked) | NEEDS VERIFICATION | Duplicates `backend/requirements.txt` with different content |
| `opencode.json` (untracked) | NEEDS VERIFICATION | Config for another tool |
| `frontend/lib/mockData.ts` | ACTIVE (1 importer) | `LLMProviderCards.tsx` |
| `frontend/app/dashboard/data.json`; `components/{section-cards,data-table,chart-area-interactive,nav-*,site-header,app-sidebar}.tsx`; `components/layout/{Sidebar,Topbar,TopNav}.tsx` (some duplicates) | NEEDS VERIFICATION | Likely shadcn dashboard scaffold leftovers alongside a custom layout; not import-traced |
| `frontend/.next/`, `backend/.pytest_cache`, `backend/.venv` | ACTIVE (build/env artifacts) | Correctly not tracked (only the one `.pyc` above is) |
| `.playgorund/` in root `.gitignore` | NEEDS VERIFICATION | Typo of "playground" |
| Duplicate `.env` files (root and `backend/.env`) | ACTIVE | See §15 |
| Analysis steps in each agent workflow (result unused) | NEEDS VERIFICATION | §6 |

---

## 15. Security Findings

Secret values are intentionally not shown.

- ⚠️ **SECRET FOUND IN `.env` (repo root)**. This file is *tracked by git* (it appears in `git ls-files` and was added in earlier commits with empty content) while also being listed in `.gitignore`, so the ignore rule has no effect. The working copy now holds a `FEATHERLESS_API_KEY` value as an uncommitted modification (`git status`: ` M .env`). A `git add -A`/`git commit -a` will commit the key. Scanning the historical `.env` blobs in `d271c2f`, `fe74a16`, `90cc99d` found no key/secret/token/password assignments, so history looked clean at audit time; a full history scan was not exhaustive across all branches. ⚪
- ⚠️ **SECRET FOUND IN `backend/.env`** (`GROQ_API_KEY`, `FEATHERLESS_API_KEY`). This file is correctly ignored (`git check-ignore` confirmed via `backend/.gitignore`) and untracked. Not a repository leak, but the same key appears in two files.
- 🟡 Recommendation for both: rotate the Featherless key if the root `.env` was ever pushed or shared; run `git rm --cached .env`.
- 🟡 `docker-compose.yml` and `DATABASE_URL` use the default password `password` and expose Postgres 5432 and Kafka 9092 on all interfaces. Acceptable for local dev; unsafe elsewhere.
- 🔴 No authentication or authorization on any API route (TDR-001: JWT). The `POST` endpoints for events/memory/runs are open. Combined with CORS credentials, this is dev-only.
- 🟡 Kafka: PLAINTEXT, no ACLs.
- ✅ No wildcard CORS. No `debug=True` found in `main.py`.
- 🟡 `create_tables.py` performs `drop_all()` against whatever `DATABASE_URL` points to, with no guard or confirmation.
- 🟡 LLM prompts embed user-supplied `goal` into templates unescaped (`PromptTemplate.format`). A goal containing `{}` braces may raise a format error. Not tested. ⚪
- Frontend `API_BASE` hardcoded to localhost. Not a secret.

---

## 16. Known Bugs

1. ⚠️ Pytest suite: 4/4 errors at setup (SQLite cannot compile `JSONB`/`Vector`), and `create_run` tests lack an event-bus override.
2. ⚠️ `test_queen.py` raises `TypeError` (missing `memory_service`).
3. ⚠️ `/system/services` reports Postgres as `offline` due to `db.execute("SELECT 1")` on SQLAlchemy 2.x (inferred, not executed). Redis is always "online" and the LLM row is fixed text.
4. ⚠️ `alembic upgrade head` on an empty DB would fail: the empty initial migration plus an FK to a non-existent `runs` table (inferred; not executed).
5. ⚠️ Run status is never updated; the `review.completed` event has no consumer; the run never reaches a terminal state.
6. ⚠️ Any agent exception is swallowed by `_dispatch`. The run hangs silently with no `run.failed`.
7. ⚠️ `/workflow/{id}/status` and `/outputs` return nothing for real runs: they read `events`, which the Scheduler never writes. `/status` treats "all stages seen" as completion, but stage names come from events the DB never stores.
8. ⚠️ `EventFeed` shows recycled historical events as live.
9. 🟡 `Settings` requires `REDIS_URL` although Redis is unused. The app will not start without it.
10. 🟡 `create_run.py` fails (missing `project_id`).
11. 🟡 `get_llm()` ignores `LLM_PROVIDER` and `agent_name`; the trailing `raise` is unreachable.
12. 🟡 The unused "analysis" LLM call in each agent workflow doubles LLM cost and latency.
13. 🟡 Embedding calls are synchronous inside async steps (blocks the event loop; 2 to 3 calls per run).
14. 🟡 The Scheduler's producer is never flushed or closed. The final `review.completed` event could be lost on process exit.
15. 🟡 `AgentLog.task_id` is non-null, which makes per-LLM-call logging impossible without inventing a Task row.

---

## 17. Architectural Gaps

1. No persistence layer for pipeline state (events, runs, tasks, agent executions, artifacts).
2. No Scheduler logic beyond a linear if-chain: no lifecycle state machine, DAG execution, retries, failure events, or DLQ.
3. No artifacts: Builder does not build; there is no artifact store or table.
4. Memory only integrated into Queen; two disjoint memory tables; no memory API/UI for `agent_memories`; no chunking; no ANN index.
5. Research is not grounded (no Tavily/web search/tools).
6. No revision/feedback loop; Guardian verdicts are inert.
7. No real-time transport to the UI.
8. No auth.
9. No observability data (agent logs empty; no token or cost capture; Loguru and DB log storage not implemented).
10. Provider abstraction is Groq only.
11. Deployment story incomplete (empty Dockerfile, no services for backend/scheduler/frontend, no `.env.example`).
12. Schema management is not reproducible (empty base migration).
13. No goal-submission UI or run-detail view for agent outputs.

---

## 18. Recommended Next Phases

Mapping findings to the phase plan. Order is by dependency.

| Phase | Scope derived from this audit |
|---|---|
| **Phase 1 — E2E Pipeline** | Start Postgres and Kafka, run one real goal through all five agents and record the result (this audit could not). Add persistence in the Scheduler: write each consumed event to `events`, update `runs.status`/`plan_text`, add a `review.completed` handler that sets a terminal status, publish `run.failed` and mark the run `FAILED` on handler errors, commit offsets after success only and dedupe by `event_id`, flush and close the Scheduler's producer. Fix the schema bootstrap (real initial migration or documented `create_all`), and fix the `/system/services` DB check. Decide the Builder/artifact question. |
| **Phase 2 — RAG** | Wire memory into Architect, Scout, Builder and Guardian (read and write); pass `project_id`/`run_id` filters; add a memory search/list API for `agent_memories` and connect the Memory page; unify or retire `memory_chunks`; async embeddings; similarity threshold/token budget; dimension/index decision. Replace unused "analysis" calls or feed their output into prompts. |
| **Phase 3 — Guardian Revision Loop** | Add `revision.requested`, Builder revision input, `revision_count` with a maximum, terminal state after max revisions. Depends on Phase 1 state handling. |
| **Phase 4 — WebSockets** | Real transport (WS or SSE) from persisted events to the UI; replace the `useEventStream` simulation; add run-progress UI. Depends on Phase 1 event persistence. |
| **Phase 5 — Testing** | Fix the test DB (run against Postgres+pgvector, e.g. a compose test service, or skip vector models under SQLite); provide an event-bus override; scope pytest to `tests/`; move manual scripts to `scripts/`; add unit tests for validators, `with_retry`, memory service, scheduler dispatch with a fake bus/LLM; fix frontend lint errors; add CI. |
| **Phase 6 — Multi-provider LLM** | Make `get_llm` honor `LLM_PROVIDER` and per-agent routing; add at least one non-Groq provider; remove the dead `BaseLLM`. |
| **Phase 7 — Production** | Fill in `backend/Dockerfile`; add backend, scheduler, and frontend to compose; healthchecks; pin the Kafka image; `.env.example`; remove `REDIS_URL` requirement; JWT auth; secrets hygiene (`git rm --cached .env`, rotate keys); Kafka topic provisioning; move the API base URL to env. |
| **Phase 8 — Documentation** | Rewrite README; add TDRs for Kafka, LlamaIndex, Groq, Featherless embeddings and `agent_memories`; correct TDR-002 topics/tables/lifecycle; refresh the diagram; fill `docs/specs/` and `docs/infrastructure/`. |

Housekeeping to schedule alongside Phase 1 (each needs explicit approval, none done in this audit): remove `agent_old.py` and `BaseLLM`; untrack the compiled `.pyc` and root `.env`; consolidate the two `requirements.txt` files.

---

## 19. Phase 0 Verification Results

What was run and what happened:

| Check | Command | Result |
|---|---|---|
| Backend tests | `backend/.venv/Scripts/python -m pytest tests -q` | ⚠️ 4 errors, 0 passed (JSONB not renderable on SQLite) |
| App import | `python -c "import app.main"` | ✅ OK |
| Agent + scheduler imports | `import agents.{queen,architect,scout,builder,guardian}.service`, `app.scheduler.consumer` | ✅ all OK |
| Bytecode compile | `python -m compileall -q agents app` | ✅ no errors |
| Alembic | `python -m alembic heads` | ✅ single head `ec1377b20fa7` (upgrade not run; no DB) |
| Ruff / mypy | `python -m ruff`, `python -m mypy` | ⚪ not installed; no backend lint or type check run |
| Frontend build | `npm run build` (Next 16.2.9) | ✅ success; 9 routes; Recharts prerender warning |
| Frontend lint | `npm run lint` | ⚠️ 26 problems: 11 errors, 15 warnings |
| Docker stack | `docker ps` | ⚪ Docker engine not running; compose stack not started |
| Live pipeline (Kafka, Scheduler, LLM, pgvector) | not executed | ⚪ NOT VERIFIED |
| Manual scripts (`test_pipeline.py`, etc.) | not executed | ⚪ would spend paid LLM/embedding credits; require live services |

Files created or modified by this audit: `docs/PROJECT-STATUS.md` (new). Running `npm run build` refreshed the git-ignored `frontend/.next/` directory, and pytest refreshed `.pytest_cache`. No source files were changed. No code was deleted.

Statements marked "inferred" (for example the `SELECT 1` bug, the Alembic fresh-DB failure, and the test event-bus gap) come from reading code against the installed library versions, not from execution.

---

# Phase 1 Implementation Results

Date: 2026-09-23. Legend: **Implemented** (code exists) · **Tested** (automated test passes) · **Live-verified** (ran against real Kafka + Postgres + real LLM) · **Not verified**.

Phase 0 findings were re-checked against the code before changing anything. Corrections to Phase 0: the root `.env` was already staged for deletion (no longer tracked); `.env.example` is no longer empty (but is still wrong, see Remaining Known Issues); the `SELECT 1` bug raises `ArgumentError`, not `ObjectNotExecutableError` (same effect).

## Event Pipeline

```
run.created → strategy.created → architecture.created → research.completed
            → tasks.generated → review.completed → run.completed
ANY handler/publish failure → run.failed
```
- `run.completed` and `run.failed` added to `EventTypes`. Existing event names unchanged. All events use the existing `KafkaEvent` envelope. The `source` field now carries the real agent names (`queen`, `architect`, `scout`, `builder`, `guardian`, `scheduler`).
- `review.completed` handler: `approved` → `run.completed`. **`needs_revision` → `run.failed` (`error_type=ReviewNeedsRevision`); `rejected` → `run.failed` (`error_type=ReviewRejected`).** There is no revision loop (Phase 3). `needs_revision` is never treated as approved; the verdict and Guardian summary are in the `run.failed` payload.
- Status: Implemented, Tested (fake agents, real Postgres, real Kafka). Live: see below.

## Run Lifecycle

- `runs.status`: `running` → `completed` | `failed` (lowercase, matching existing data). `duration_ms` is set on both terminal transitions. No `updated_at`/`completed_at` columns were added (smallest change; duration + the terminal event's timestamp cover it).
- Events arriving for a run that is already terminal are ignored (no further agent execution).
- If `run.created` cannot be published by the API, the run is set to `failed` instead of staying `running`.
- Implemented, Tested.

## Event Persistence

- Single ownership model: **the Scheduler persists every event it consumes**, including the ones it produced earlier (they are always consumed back via Kafka, so nothing is written twice). `events.id` = Kafka `event_id`; `agent` = `source`; `created_at` = event timestamp; `payload` = full payload. No new table.
- The `events` primary key doubles as the processed-event ledger.
- `/workflow/{id}/status` now reports `status`, `is_completed`, `current_stage`, `failure`; `/outputs` reads the persisted payloads.
- Implemented, Tested. Live-verified only for the partial runs (run.created, strategy.created, run.failed rows were written and read back through the API).

## Failure Handling

Per event, in order: duplicate? → skip. Unknown/terminal run? → skip. Run handler. Publish next event (blocking, delivery-confirmed). One DB transaction: consumed-event row + effects. Commit Kafka offset.

- Handler exception **or** failure to publish the next event → publish `run.failed` (payload: `failed_stage`, `error_type`, `message`; configured API keys are masked, message capped at 500 chars) → persist the failing event → commit offset (the failure is recorded, never retried, so no retry storm).
- If `run.failed` itself cannot be published (Kafka down), the run is marked `failed` and the `run.failed` event row is written directly in PostgreSQL.
- Infrastructure error (DB unreachable, offset commit failing): offset **not** committed; consumer seeks back to the message and retries every 5 s.
- Undecodable message: logged, offset committed, skipped (it cannot be tied to a run).
- Implemented, Tested. **Live-verified**: a real LLM error (model not available / rate limit / timeout) produced `run.failed` and `runs.status=failed` within seconds in 4 real runs.

## Idempotency

- Application-level, PostgreSQL-backed, survives restarts. Not exactly-once.
- Child event ids are `uuid5(parent.event_id, child_type)`. If the scheduler crashes after publishing a child but before the DB commit, the redelivered parent re-emits a child with the same `event_id`, which is deduplicated on consumption. The only work that can repeat in that window is the agent call itself (at-least-once).
- Implemented, Tested (duplicate delivery, crash-window redelivery, scheduler restart mid-run, fresh consumer group re-reading the whole topic on real Kafka: no agent re-executed).

## Kafka Reliability

- `enable.auto.commit=False`; `consumer.commit(message, asynchronous=False)` only after processing.
- `KafkaEventBus.publish` now blocks until delivery is acknowledged and raises `EventPublishError` on failure or timeout (`message.timeout.ms=10000`). Previously it returned before delivery.
- Scheduler shutdown closes the consumer and flushes/closes its producer (`start()` `finally`).
- `max.poll.interval.ms` raised to 30 min so long agent chains do not trigger a rebalance.
- Implemented, Tested (real broker + fake consumer semantics).

## Task Persistence

- Builder's `TaskGraph` is written to `tasks` in the same transaction as the `research.completed` event row. Task ids are deterministic (`uuid5` of run id + Builder task id) and `depends_on` is remapped to those ids.
- Schema change: `tasks` gained `title`, `description`, `details` (JSON: priority, estimated_complexity, required_files, acceptance_criteria). Migration `a1c4e7d90b12`. `type="build"`, `status="pending"`.
- Implemented, Tested. Not live-verified (no live run reached the Builder).

## Schema Bootstrap

- The initial Alembic migration `31ac285a6970` was empty; it now creates `projects, runs, tasks, events, memory_chunks, agent_logs`. Chain: `31ac285a6970 → ec1377b20fa7 (agent_memories) → a1c4e7d90b12 (task columns)`.
- **Verified on a fresh empty pgvector database** (`hivemind_migtest`): `alembic upgrade head` succeeds, `alembic check` reports "No new upgrade operations detected", `downgrade base` and re-`upgrade head` succeed. The existing dev DB was upgraded (additive) too.
- `create_tables.py` (git-ignored, dev-only) now exits unless `--i-understand-this-drops-all-data` is passed; it is not used by app startup.
- `/system/services` DB check now uses `text("SELECT 1")` and reports PostgreSQL `online` (live-verified). The Redis/LLM rows are still hardcoded (Phase 7/8).

## Testing

`cd backend && pytest` (scoped to `tests/` by `pytest.ini`): **31 passed, 0 failed, 0 skipped.**
- Test DB: real PostgreSQL + pgvector (`hivemind_test`, created from `template0`, built with `alembic upgrade head`). No SQLite, no model changes. Requires `docker compose up -d`. Uses dummy API keys only; no LLM credits.
- `tests/test_scheduler.py` (25 cases, fake bus + fake agents): full lifecycle + task rows + workflow API, running-stage reporting, non-approved verdicts, failure at each of the 5 stages, key masking, publish failure, Kafka-down failure fallback, terminal-run ignore, unknown run, duplicate event, crash-window redelivery, restart mid-run, offset commit/seek/poison semantics, producer close on shutdown, `KafkaEventBus` raising when delivery fails, run creation failure, `/system/services`.
- `tests/test_e2e_kafka.py` (3 cases, marker `kafka`, auto-skips without a broker): real API lifespan producer + real scheduler consumer thread + real Kafka topic + fake agents + Postgres: completes with 7 ordered events and 2 tasks; failure at Scout → `failed`; fresh consumer group re-reading the topic → no agent re-executed.
- The pre-existing 4 API tests (projects/runs) now pass.
- Root-level `backend/test_*.py` scripts are unchanged, manual, and excluded from pytest by `pytest.ini`; `test_queen.py` is still stale.
- Frontend not touched; `npm run build` not re-run.

## Live E2E Verification

**Result: the full happy path was NOT verified live.** Not verified: Scout, Builder, Guardian, `run.completed` and task rows with a real LLM.

Environment: docker compose Postgres (pgvector) + Kafka up, FastAPI (uvicorn) and Scheduler running, goal "Build a technical plan for a web application that tracks personal expenses, including architecture, database design, API design, and testing strategy."

| Run | Model | Result |
|---|---|---|
| `865a8613…` | `llama-3.3-70b-versatile` (configured) | `failed` at queen in 9.9 s: Groq 404 model not available to this key. events: run.created, run.failed |
| `56adb124…` | `openai/gpt-oss-120b` | `failed` at queen in 40.8 s: Groq 400 tool_use_failed (structured-output tool call mismatch through LlamaIndex) |
| `341495b2…` | `qwen/qwen3.8-27b` | Queen OK (`strategy.created` persisted); `failed` at architect in 89.6 s: LlamaIndex Workflow default 45 s timeout |
| `6c3d46b5…` | `qwen/qwen3.8-27b`, 300 s timeout | Queen OK; `failed` at architect in 81.2 s: Groq 429, output-tokens-per-minute limit 1000 vs ~1900 requested (both retries) |

What this proves live: real Kafka round-trip API → Scheduler → Kafka → Scheduler, event persistence, Queen→Architect chaining, run status transitions, `run.failed` with diagnosable payload, `/workflow/{id}/status` and `/outputs` returning persisted data, manual offset commits, no hung runs. The blocker is the available credentials/rate limit, not the pipeline. Non-default models (`LLM_MODEL` env override on the scheduler process only; `.env` files untouched) were used for runs 2-4.
Also observed: the Featherless embedding key returns 401, so Queen's memory read/write silently degrades (0 `agent_memories` rows); Queen's memory behavior is therefore **not verified live**.

To finish live verification: provide a Groq key/model with enough output-token budget (or set `LLM_MODEL`), and a valid `FEATHERLESS_API_KEY`, then submit a run and expect 7 events, tasks rows and `completed`.

Housekeeping: the dev database now contains these 4 failed live runs.

## Remaining Known Issues

- Live happy path unverified (see above); Scout/Builder/Guardian never ran against a real LLM in this phase.
- The configured `LLM_MODEL` default (`llama-3.3-70b-versatile`) is not available to the current Groq key; `get_llm` still ignores `LLM_PROVIDER`/`agent_name` (Phase 6). `gpt-oss-*` fails LlamaIndex structured output on Groq.
- Added `AGENT_TIMEOUT_S` (default 300) because LlamaIndex Workflow's 45 s default made slower models fail. Not a Phase 0 finding.
- `.env.example` is still wrong: DB user `postgres` (compose uses `hivemind`), `KAFKA_GROUP_ID` (config reads `KAFKA_CONSUMER_GROUP`), missing required `REDIS_URL`. `REDIS_URL` is still required by `Settings` (Phase 7). Tracked `backend/requirements.txt` is still incomplete (Phase 7).
- Agent calls can repeat in the narrow crash window between publish and DB commit (at-least-once); the API `POST /runs` blocks on Kafka delivery.
- A failed run is not retried; there is no scheduler retry policy or DLQ. Undecodable messages are dropped.
- `agent_logs` still unwritten; `Run.plan_text`/`success_criteria` still unpopulated; Guardian revision loop, WebSockets, memory for other agents, auth, Dockerfile: unchanged (later phases).
- Frontend: `useEventStream` still replays old events; frontend lint errors unchanged.
- Pre-existing dead code (`agent_old.py`, `BaseLLM`, etc.) untouched.

---

# Groq-Only LLM Migration

Date: 2026-09-23. This section supersedes the Phase 0/Phase 1 statements above about Featherless, `LLM_PROVIDER`, model availability and the unverified live happy path; those sections are kept as the historical record.

## Groq-Only LLM Migration

**Result: COMPLETE for the LLM; memory (embeddings) is a separate, documented blocker.**

- **Provider / model:** Groq, `openai/gpt-oss-120b`, through LlamaIndex. `LLM_PROVIDER` was removed (no misleading provider switch). `LLM_MODEL` defaults to `openai/gpt-oss-120b` in `Settings`; `GROQ_API_KEY` is required; `AGENT_TIMEOUT_S` (default 300) is still honoured by every workflow; new `LLM_REASONING_EFFORT` (default `low`).
- **One LLM path:** `agents/llm/factory.py::get_llm()` (no per-agent argument any more) → `GroqLLM` → one `Groq(...)` constructor. All five agent services call `get_llm()`. Tested: every agent's workflow LLM is the same Groq instance type/model.
- **Startup logging:** API and Scheduler log `LLM Provider: Groq | LLM Model: openai/gpt-oss-120b | reasoning_effort=low | agent_timeout=300.0s` and the embedding status. Never the key (tested).
- **Featherless removed:** its client/provider class, `FEATHERLESS_API_KEY`, `EMBEDDING_MODEL` and the key-masking entry are gone from `app/`, `agents/`, tests, `.env.example` and `backend/.env`. `git grep -i featherless` on tracked files (excluding this document) returns nothing; a test asserts the runtime code stays clean. Local, non-runtime leftovers (not touched): the repo-root `.env` (untracked/ignored; contains only the now-dead key and is not read by the backend), `opencode.json` (untracked config for a different tool, not HiveMind).
- **`.env.example` rewritten** to the actual variables (verified against `Settings`): `DATABASE_URL` (user `hivemind`, matching compose), `KAFKA_*` (`KAFKA_CONSUMER_GROUP`), `GROQ_API_KEY`, `LLM_MODEL`, `LLM_REASONING_EFFORT`, `AGENT_TIMEOUT_S`, `EMBEDDING_PROVIDER=none`, `CORS_ORIGINS`. `REDIS_URL` no longer required (unused; defaults). `.env` is untracked and ignored (`git ls-files .env` empty, `git check-ignore -v .env` matches).
- **Docker:** `docker-compose.yml` has only Postgres and Kafka (no Featherless, nothing to pass); there is still no backend/scheduler container and `backend/Dockerfile` is empty (Phase 7), so nothing in Docker consumes `GROQ_API_KEY`/`LLM_MODEL` yet.
- Also fixed: `/system/services` LLM row said "Gemini Flash"; it now reports `Groq · <LLM_MODEL>` (latency/status fields are still placeholder values). TDR-001 got a "Current implementation" note (Groq only; provider list is design intent).

## Structured Output (gpt-oss-120b)

**Why the old path failed:** `llama_index.llms.groq.Groq` sets `is_function_calling_model=True`, so `llm.astructured_predict` forces `tool_choice="required"` with a single tool named after the schema. gpt-oss answers with a tool name that is not in `request.tools` and Groq rejects the call (400 `tool_use_failed`, "attempted to call tool 'analyze_goal' which was not in request.tools"). Raising retries cannot fix that.

**New path (`agents/base/structured.py`, used by `with_retry` for every agent and by Queen's goal analysis):**
1. Render the existing prompt, append the Pydantic model's JSON Schema and a "JSON object only" instruction.
2. Call `llm.acomplete(prompt, response_format={"type": "json_object"})` (Groq JSON mode).
3. Extract the JSON object (plain, ```json fenced, or wrapped in prose).
4. Validate with `output_cls.model_validate_json`. Non-JSON, arrays, missing fields and wrong types raise `StructuredOutputError`.
5. `with_retry` (2 attempts) re-prompts with the validation error as feedback; after the last failure it raises `GenerationError`, which the Scheduler turns into `run.failed`.
6. The agents' existing business validators (sequential ids, dependency checks, verdict values, ...) still run afterwards; the agent output schemas and Kafka payloads are unchanged.

`reasoning_effort=low` is passed on every call: in a probe it cut completion tokens for the same schema from 374 to 152 (reasoning tokens count against output-token limits).

## Token Budget / Timeouts

- No agent-specific `max_tokens` was set (arbitrary caps risk truncating JSON). Output budget is controlled by `reasoning_effort=low` and schema-only output. `AGENT_TIMEOUT_S` default stays 300 s (the LlamaIndex default of 45 s is too short for a reasoning model); a 1 s value was used only to force a failure in the live failure test.
- Live run: Groq returned HTTP 429 six times (tokens-per-minute pressure) on Builder and Guardian; the OpenAI client's built-in backoff (6-14 s waits) absorbed all of them, so those stages took ~13 s instead of ~3 s. No run failed on rate limits with `gpt-oss-120b`.
- Known waste, not changed (would alter agent workflows): the "analysis" LLM call in Architect/Scout/Builder/Guardian is still made and its output unused (Phase 0 §6). It costs one extra call per agent and adds to the 429 pressure.

## Memory / Embeddings

- **Vector DB: PostgreSQL + pgvector, schema untouched** (`agent_memories.embedding Vector(4096)`, migration unchanged, `alembic check` clean).
- **Embedding provider: none.** Groq has no embedding models and no other implementation exists in the repo (the only one was Featherless). `EMBEDDING_PROVIDER` defaults to `none`; any other value raises `ValueError` at `MemoryService()` construction. `BaseEmbeddingProvider` and `MemoryService(embedding_provider=...)` remain as the extension point.
- **Queen policy (intentional, explicit):** `EMBEDDING_PROVIDER=none` → Queen logs `Memory disabled (EMBEDDING_PROVIDER=none)` for retrieval and for storing and continues; nothing is pretended to be stored. A configured provider that fails (401, network, bad vector) now **raises and fails the run** (`run.failed`); the old `try/except ... logger.warning` that swallowed it is gone.
- Tested against real PostgreSQL + pgvector with a deterministic fake 4096-d embedding provider: store on run 1, cosine search finds it on run 2 and injects it into the strategy prompt; a failing provider fails the Queen workflow and stores nothing. **Not live-verified** (no real embedding provider). **Queen memory: BLOCKED (disabled) until an embedding provider is chosen and implemented.**

## Automated Verification

- `pytest -q` (from `backend/`): **56 passed, 0 failed, 0 skipped** (was 31). New `tests/test_llm_groq.py` (25 tests): single-provider config, all agents share one Groq model, startup log without key, no Featherless in runtime code, structured parsing accept/reject cases, JSON-mode call shape, retry with feedback, malformed output rejected, all five agents producing their Pydantic schemas from JSON text, business-rule rejection, Queen memory disabled / roundtrip / failing. Existing Kafka lifecycle, failure, dedup and offset tests unchanged and passing. No test calls Groq.
- `alembic check`: **No new upgrade operations detected.** (Also fixed `alembic/env.py` calling `fileConfig` without `disable_existing_loggers=False`, which silently disabled application loggers whenever migrations ran in-process.)
- `git grep -i featherless` (tracked, excl. this document): none.

## Live E2E (real stack, configured model, no overrides)

Stack: docker compose Postgres+pgvector and Kafka, uvicorn API, Scheduler, real Groq `openai/gpt-oss-120b`. Startup logs showed Groq / `openai/gpt-oss-120b`, memory disabled, no secrets. Health: `/health` ok; `/system/services` PostgreSQL online.

**Happy path: VERIFIED.** Run `88333bf6-f966-40e8-9ca2-39df8ad6d25f`, goal "Build a technical plan for a web application that tracks personal expenses...", 2026-09-23 16:59:25 → 17:00:59 UTC.
- Events in PostgreSQL, in order, one each: `run.created` → `strategy.created` (queen) → `architecture.created` (architect) → `research.completed` (scout) → `tasks.generated` (builder) → `review.completed` (guardian) → `run.completed` (scheduler).
- `runs.status=completed`, `duration_ms=94017`.
- `tasks`: 5 rows (Define Architecture → Design Database Schema → Specify API Contracts → Develop Testing Strategy → Compile Documentation & Review) with `depends_on` mapped to task ids.
- Guardian executed for real: verdict `approved`. `/workflow/{id}/status` and `/outputs` return all 5 agent outputs (5 phases, 5 components, 4 findings, 5 tasks).
- Queen memory: skipped explicitly (disabled); 0 `agent_memories` rows.

**Failure path: VERIFIED live.** Scheduler started with `AGENT_TIMEOUT_S=1` (real stack, real model, forced Queen timeout): run `a71d8799-…` → events `run.created`, `run.failed`; `runs.status=failed`; payload `{failed_stage: queen, error_type: WorkflowTimeoutError, message: "Operation timed out after 1.0 seconds..."}`; nothing left in `running`. Kafka offset for the failed event was committed (later replays skipped it as a duplicate instead of re-running it).

**Restart / redelivery: VERIFIED live.** Run `947286b2-…`: the Scheduler process was killed (`Stop-Process -Force`) while Scout was executing (after `architecture.created` was consumed, before its row/offset commit). Only `run.created` and `strategy.created` were in the DB. After restart Kafka redelivered `architecture.created`; agent executions across both processes: Queen 1, Architect 1, Scout 1 (the interrupted call never completed, so it ran once), Builder 1, Guardian 1. Events: exactly 7 rows, 0 duplicate ids, 10 task rows. The run reached a terminal state: `failed`, because the live Guardian returned `needs_revision` (`ReviewNeedsRevision`), which is the documented Phase 1 policy; this also exercised the non-approved-verdict path with a real model.

**Duplicate delivery: VERIFIED live.** A Scheduler with a brand-new consumer group re-read the whole topic from the beginning: 26 events skipped as `Duplicate event`, 0 agent calls, 0 errors, `events` (48) and `tasks` (30) counts unchanged. Guarantee is at-least-once delivery plus application-level idempotency, not exactly-once.

## Remaining Limitations

- **Queen memory disabled** until an embedding provider exists (blocker; the vector store itself is intact and tested).
- Under Phase 1 policy a Guardian `needs_revision`/`rejected` fails the run. With this model that happens on realistic runs (1 of 2 full live runs); the revision loop is Phase 3.
- Groq free-tier token limits cause 429 backoff delays (~10-14 s per hit); no failures observed, but throughput is limited. The unused per-agent "analysis" calls add to it.
- Cosmetic: after each handler the log shows `Task exception was never retrieved ... Event loop is closed` from an httpx client cleaning up after `asyncio.run` closed its loop. Harmless (all runs succeeded) but noisy.
- 3 pre-existing runs (seed `run_002` and two manual runs from before Phase 1) show `running` with no events; they predate the new scheduler and will never advance.
- Unchanged from earlier phases: no backend/scheduler Docker service or Dockerfile, hardcoded Redis/latency placeholders in `/system/services`, frontend `useEventStream` replay, no auth, TDR-002 still describes a provider-agnostic design (intent, not implemented).

---

# Phase 2 — Persistent Semantic Memory

Date: 2026-09-23. This section supersedes the earlier statements that Queen memory is disabled / blocked (Groq-Only LLM Migration section) and the Phase 0 memory findings (§7) about Featherless and the 4096-d column.

## Audit (before changes)

- **Authoritative memory:** `agent_memories` (+ `app/memory/*`), pgvector. `memory_chunks` (`/api/v1/memory`, seed/mock data for the Memory page) is a separate legacy table with no vectors; untouched and not merged (out of scope).
- **State found:** `agent_memories` had 0 rows, `Vector(4096)`, no ANN index, pgvector 0.8.6. Only Queen used it; nothing had ever been persisted or retrieved in a real run (the sole embedding provider was Featherless, now gone).

## Architecture

```
LLM:         Groq · openai/gpt-oss-120b            (reasoning, extraction proposals)
Embeddings:  fastembed (local ONNX) · BAAI/bge-small-en-v1.5 · 384 dimensions
Vector DB:   PostgreSQL + pgvector · agent_memories · HNSW (cosine)
```
- **Why fastembed/bge-small:** Groq has no embedding models; no other embedding API key exists; the model is free, needs no key, runs on CPU without PyTorch (ONNX), is deterministic (verified: identical vectors on repeat calls, unit-norm) and downloads once (~130 MB) into `backend/.model_cache/` (git-ignored). Measured 0.3 s to embed 10 texts.
- **Boundary:** `app/memory/embeddings.py::EmbeddingService` (`embed_text`, `embed_texts`, `dimension`, async via `asyncio.to_thread`) is the only thing the rest of HiveMind uses; the SDK lives in `FastEmbedBackend`. It validates input (non-empty string, ≤ 2000 chars), turns any provider error into `EmbeddingError`, never logs secrets, batches in one call, and **rejects vectors whose size ≠ `EMBEDDING_DIMENSION`** (no padding/truncation). `get_embedding_service()` is a per-process singleton; `EMBEDDING_PROVIDER=none` disables memory explicitly.
- **Fail fast:** the Scheduler warms the model at startup (loads it, checks the vector size) and exits with code 1 on a bad model name or a dimension mismatch (both verified live) instead of failing mid-run.
- Config (`.env.example` updated): `EMBEDDING_PROVIDER=fastembed`, `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`, `EMBEDDING_DIMENSION=384`, `MEMORY_TOP_K=5`, `MEMORY_MIN_SIMILARITY=0.60`, `MEMORY_MAX_PER_RUN=3` (plus `MEMORY_DEDUP_SIMILARITY=0.95`, `EMBEDDING_CACHE_DIR`).

## Vector dimension and schema (migration `b7e2f1a93c55`)

- Column changed `vector(4096)` → **`vector(384)`** (`alembic check` clean; ORM reads `EMBEDDING_DIMENSION`, so a config/DB mismatch shows up as drift). Vectors from different models are not comparable, so the migration **refuses to run if `agent_memories` has rows** (no truncate/pad/silent drop): verified on a scratch DB with a 4096-d row (RuntimeError with instructions), then success after clearing. The dev table was empty, so the migration applied directly. Downgrade also refuses when rows exist.
- New/changed columns: `project_id` (NOT NULL, FK `projects`) = **scope**; `source_event_id` = provenance; `importance` (1-5, CHECK); `content_hash` (sha256 of normalised content) = dedup key. Existing: `agent` (ownership), `run_id` (source run), `memory_type`, `content`, `embedding`, `metadata_`, timestamps.
- Constraints/indexes: CHECK `memory_type IN (fact, decision, preference, context, lesson)`; UNIQUE `(project_id, memory_type, content_hash)`; **HNSW index `vector_cosine_ops`** on `embedding` (dimension ≤ 2000 is what makes this possible; the 4096-d column could not be indexed). Verified with `EXPLAIN` (seq scan disabled) that the cosine `<=>` ORDER BY uses `ix_agent_memories_embedding_hnsw`.
- Fresh database: `downgrade base` + `upgrade head` (4 migrations) succeed; `alembic check`: no drift.

## Memory types, extraction, storage

- `MemoryType` enum: `fact`, `decision`, `preference`, `context`, `lesson` (also a DB CHECK). The bogus `MemoryType` in the old model file (wrong `Enum` import) was removed.
- **Extraction (Queen):** after the strategy passes validation, one extra Groq call (`QUEEN_MEMORY_PROMPT`, strict `MemoryExtraction` schema through the same JSON-mode/validate/retry path as every agent) *proposes* up to 3 durable memories. What is stored is decided deterministically by `sanitize_candidates`: allowed type, 10-500 chars, importance 1-5, **no secrets**, no duplicates, cap `MEMORY_MAX_PER_RUN`, best importance first. Whole strategies, prompts, phase/task lists and Kafka events are never stored (tested).
- **`store_memory`:** validate → secret check → exact-hash dedup (no embedding call) → embed → semantic dedup → `INSERT … ON CONFLICT DO NOTHING` → commit, one transaction, rollback on any error. Embedding failure raises `MemoryStoreError("… memory NOT stored")`; DB failure raises `MemoryStoreError` and leaves the session usable; a memory row is never written with a fake/null vector.
- **Deduplication:** exact (normalised, case/whitespace-insensitive) per `(project, type)` **and** semantic (same project + type, cosine ≥ 0.95). Same text under a different type or project is kept. Repeat runs do not multiply memories (tested: 3 runs → 1 row).
- **Conflict policy (deliberate, simple): retain both with provenance.** No supersede/consolidation logic: "uses Redis" and "uses Kafka" are both kept, each with `run_id`/`source_event_id`/`created_at`. Recency/consolidation is future work.

## Retrieval

- `retrieve_memories(db, query, project_id, top_k, min_similarity, memory_types, agent)`: embed query → pgvector cosine distance → filter `project_id` (scope), optional type/agent → similarity ≥ threshold → order by similarity then importance → top-K (default K=5, threshold 0.60). Similarity metric is cosine only (`similarity = 1 - cosine_distance`). Empty DB / empty query → `[]` (not an error). Embedding or pgvector errors raise `MemorySearchError`.
- **Threshold, measured (not guessed):** relevant pairs in this project scored 0.65-0.82; unrelated pairs 0.45-0.58 (unrelated-but-same-domain up to ~0.61). Default lowered from a first guess of 0.65 to **0.60** after a real run showed a relevant memory at exactly 0.650.
- **Prompt context** (`format_memory_context`, deterministic): `Relevant HiveMind Memory:` + `N. [type] content`, best first; `No relevant memories found.` when empty. No ids, scores or vectors reach the LLM.
- Logs (no memory text, no vectors): `Memory retrieval started`, `Memory retrieval completed: N results (best similarity X)`, `No relevant memories found`, `Memory stored: type=… importance=…`, `Memory deduplicated (exact|semantic|concurrent)`, `Memory extraction: kept N, dropped {...}`, `Embedding provider error`, `Memory persistence error`, `Memory rejected: content looks like a secret (label)`.

## Scope policy and limitation

- Scope = **project** (`agent_memories.project_id`); Queen receives the project id from the `run.created` payload. Retrieval never crosses projects (tested with two projects). There is no user/tenant identity or authentication in HiveMind yet, so anyone who can create a run in a project shares that project's memory. No global (cross-project) memory exists.

## Security

- `app/memory/security.py::find_secret` (deterministic regexes, not prompts): API-key formats (`gsk_`, `sk-`, …), GitHub/AWS/Slack tokens, JWTs, `Authorization`/Bearer, `scheme://user:pass@`, private-key headers, `password/secret/token/api_key = value`, long random tokens. Applied twice: extraction drops matching candidates, and `store_memory` raises `MemorySecretError` for anything that reaches it. Tested with 11 secret samples (none stored) and 4 ordinary sentences (not flagged). Deliberately biased toward false positives (a dropped memory is cheap).

## Failure behavior (intentional policy)

- **Configured memory is required:** if embedding, PostgreSQL or pgvector fails during Queen retrieval or storage, the exception propagates, Queen's step fails and the Scheduler emits `run.failed` (Phase 1 path). Nothing is swallowed and no run claims memory was stored when it was not. `EMBEDDING_PROVIDER=none` is an explicit opt-out (Queen logs `Memory disabled`).
- Empty memory DB is normal. Extraction LLM failure (after 2 retries) also fails the run under the same policy.

## Automated tests

`cd backend && pytest -q`: **117 passed, 0 failed, 0 skipped** (was 56; +61). `alembic check`: clean. `tests/test_memory.py` (61) runs against real PostgreSQL + pgvector; logic tests use a deterministic hashing backend, semantic-quality tests use the real bge-small model (auto-skipped if the model cannot load). Coverage: embedding dimension/validation/batching/provider failure/wrong-dimension rejection; factory; DB column dimension = 384; vector persisted at full size with provenance; HNSW index used by the cosine query; exact + semantic dedup, per-type/per-project keeping, conflicting memories both kept; embedding/DB failure = no success + rollback; request validation; DB CHECK on types; disabled memory; semantic ranking, threshold filtering, top-K, type and agent filters, project isolation, empty DB, empty query, embedding/pgvector failure; persistence across recreated service/session; real-model examples (`What database does HiveMind use?` → only the PostgreSQL memory; paraphrase hit; unrelated query → nothing; reworded duplicate deduplicated); 11 secret samples; extraction guardrails; context format; Queen (empty DB, relevant memory injected and irrelevant/other-project excluded, only extracted durable memories stored with provenance, transient output and secrets not stored, repeat runs deduplicated, cross-run persistence with fresh service objects, explicit failure on embedding error at retrieval and at storage); logs contain no memory text or vectors. Phase 1 lifecycle/idempotency/Kafka tests unchanged and passing.

## Live memory test (real stack: Groq gpt-oss-120b + local bge-small + Postgres/pgvector + Kafka)

Project `ea2c04de-…` (HiveMind Demo Project). Startup log: `LLM Provider: Groq | LLM Model: openai/gpt-oss-120b …` and `Embedding provider: fastembed:BAAI/bge-small-en-v1.5 (384d) | vector DB: PostgreSQL + pgvector`.

- **Run 1** `598ff03e-…`: goal states two project decisions (PostgreSQL only, TypeScript frontend). Retrieval: `No relevant memories found` (empty DB). **Stored 3 memories, verified in `agent_memories`**: decision "The application must use PostgreSQL as its only database." (importance 5), decision "The frontend must be written in TypeScript." (5), context "The project is a personal expense tracking web application." (4), each with a 384-d vector (`vector_dims = 384`), the project id, run id and source event id. The strategy text itself was not stored.
- **Run 2** `abc8fc11-…` (different goal: "Design the data storage layer and the user interface technology for the expense tracker monthly reports feature."), the Scheduler process that ran Run 1 still running: `Memory retrieval completed: 1 results (best similarity 0.721)` → the Run-1 context memory was retrieved and injected. **Cross-run persistence: VERIFIED** (memory written by Run 1 was retrieved by a later run).
  - **Limitation observed:** the two decisions that mattered most scored only 0.52 against this goal's wording ("data storage layer", "user interface technology" vs "database", "TypeScript"), below the 0.65 threshold in force then, so they were *not* injected and the Run-2 strategy did not mention PostgreSQL/TypeScript. A directly worded goal ("Which database and frontend language should the expense tracker use?") scores them 0.650/0.659. A small embedding model matching short goal text against terse facts is weak on paraphrase; the threshold is a precision/recall knob (`MEMORY_MIN_SIMILARITY`), not a solved problem.
- **Run 3** `c3c787be-…` (after lowering the threshold to 0.60 and restarting the Scheduler): `Memory retrieval completed: 4 results (best similarity 0.811)` → 4 memories from Runs 1-2 injected (context, plus three expense-schema/testing memories from Run 2); the PostgreSQL decision scored 0.599, 0.001 under the threshold. 3 new memories stored (`new=3`, none deduplicated). The reconstruction of scores/injected context was done by re-running the same retrieval against the stored memories.
- **Fail-fast:** `EMBEDDING_DIMENSION=768` → Scheduler exits 1 with `Embedding has 384 dimensions, expected 768 … Refusing to pad or truncate`; `EMBEDDING_MODEL=does-not/exist` → exits 1 with `Model … is not supported`.
- Extraction quality note: some LLM-proposed memories are generic ("Clarify expense reporting requirements before designing …"). They pass the deterministic guardrails but have low reuse value; prompt tuning is future work.

## Existing pipeline with memory integrated (Run 3)

`run.created → strategy.created → architecture.created → research.completed → tasks.generated → review.completed → run.completed`, all 7 events in PostgreSQL, `runs.status=completed`, `duration_ms=122634`, 8 task rows, Guardian executed and returned `approved`. Runs 1 and 2 ran the same six agent stages but ended `run.failed` because Guardian returned `needs_revision` (Phase 1 policy: no revision loop; Phase 3). So 1 of 3 live runs completed; memory behaviour was identical in all three. Kafka idempotency/offset tests still pass (automated); not re-run live in this phase.

## Remaining limitations

- Recall: paraphrase/indirect goal wording can fall under the threshold (see Run 2); goal-only queries; no query expansion or re-ranking; one embedding model.
- Memory is only used by Queen (Architect/Scout/Builder/Guardian neither read nor write it); `memory_chunks` (UI) and `agent_memories` are still two unrelated tables and there is no API/UI for `agent_memories`.
- No consolidation/supersede or expiry; conflicting memories accumulate (both kept). Extraction quality depends on the LLM (generic memories occur).
- Scope is project-level only; no user identity/auth; no per-user privacy.
- Sync DB calls inside async steps; extra Groq call per run (+1 with reasoning) adds to 429 pressure.
- The embedding model is a local ~130 MB download on first start (needs network once); CPU inference.
- Runs still fail when Guardian says `needs_revision` (Phase 3). No backend container/Dockerfile yet, so the model cache is not baked into any image.

---

# Phase 3 — Guardian Revision Loop

Date: 2026-09-24. Supersedes the Phase 1 policy (`needs_revision` → `run.failed`) and the "Guardian revision loop: missing" findings above.

## Event lifecycle

```
Approved:  run.created → strategy.created → architecture.created → research.completed
           → tasks.generated → review.completed → run.completed

Revision:  … tasks.generated → review.completed (needs_revision)
           → revision.requested → tasks.generated → review.completed → (approved) run.completed
           (repeat revision.requested → tasks.generated → review.completed until approved or the limit)

Rejected:  review.completed (rejected) → run.failed (ReviewRejected)
Limit:     review.completed (needs_revision, revision_count >= MAX_REVISIONS) → run.failed (MAX_REVISIONS_EXCEEDED)
Failure:   any handler / Builder / Guardian error or publish failure → run.failed
```
- **One new event, `revision.requested`** (already listed in TDR-002 as a design topic). Its payload: the previous `architecture_plan`, `research_report` and `task_graph`, `revision_number`, and a strict `revision` object (`RevisionRequest`).
- Every event now carries `revision_number` (0 = the original Builder output). `tasks.generated` and `review.completed` payloads now carry the full context forward (plan, research, task graph, validation report), which the loop needs.
- Every event id is unique and deterministic: children are `uuid5(parent.event_id, type)`. The revision `tasks.generated` is a child of `revision.requested`, so it never reuses the original's id.

## Revision payload (`agents/guardian/revision.py::RevisionRequest`, Pydantic, strict)

`run_id`, `revision_id`, `revision_number` (≥ 1), `max_revisions`, `source_review_event_id` (the `review.completed` that asked), `reason` (Guardian summary), `feedback` (≥ 1 item; the review areas Guardian flagged, or every area if none was flagged), `requested_changes` (≥ 1 item; Guardian's recommendations, or its summary if it gave none). Validators: number ≤ `MAX_REVISIONS`; `revision_id` must equal the derived id. Built by code from the validated `ValidationReport`, never from free text. The handler re-validates the Guardian report with Pydantic first; invalid output (missing verdict, unknown verdict, empty) fails the run instead of looping.

## Loop control (in code, not in the LLM)

- `MAX_REVISIONS` (config/env, default **3**; `.env.example` updated). `revision_count` = the `revision_number` of the output just reviewed (0 before the first revision). `needs_revision` and `revision_count < MAX_REVISIONS` → `revision.requested` (number = count + 1); otherwise `run.failed` with `error_type=MAX_REVISIONS_EXCEEDED`, `revision_count`, `max_revisions`, and the Guardian's `feedback` and `requested_changes` (not hidden). `MAX_REVISIONS=0` disables the loop.
- `rejected` → `run.failed` (`ReviewRejected`), no revision. `approved` → `run.completed` (payload includes `revision_count`).

## State and persistence

- **`runs.status` is unchanged** (`running`/`completed`/`failed`). A separate REVIEWING/REVISING state machine would duplicate information already in the revision rows, so revision state lives in `run_revisions`; `completed` is only set by `run.completed`, so the DB can never say `completed` while a revision is pending (tested step by step through the API).
- **`run_revisions` (new table, migration `c3d5a8e2f714`), one row per revision, history never overwritten:** `id` (= `revision_id`, deterministic `uuid5(run : source review : number)`), `run_id`, `revision_number`, `source_review_event_id`, `reason`, `feedback`, `requested_changes`, `status` (`requested` → `revised` → `approved` | `needs_revision` | `rejected`; `failed` if the run fails mid-way), `tasks_event_id` (Builder output that followed), `review_event_id` (review that judged it), `created_at`, `completed_at`. UNIQUE(run_id, revision_number), CHECK on status and number ≥ 1. This answers: how many revisions, which review caused each, what feedback was given, what Builder output followed, which revision finally passed.
- **Tasks:** `tasks.revision_number` (default 0). Revision N tasks are new rows with deterministic ids; original tasks are kept. The current task set is the highest `revision_number`; `/workflow/{id}/outputs` returns the latest `task_graph`/`validation_report` and `current_revision`.
- **Workflow API:** `/workflow/{id}/status` now also returns `revision_count`, `max_revisions`, `current_revision`, `revision_status` (`none` when no revision) and a `revisions` list; `current_stage` is derived from the last event (stages repeat during revisions). No other API changes.
- Same transaction rule as Phase 1: publish downstream (blocks for Kafka ack) → one DB transaction (consumed-event row + revision row/status + revised tasks) → commit offset.

## Builder revision

`revision.requested` → `BuilderService.revise_task_graph` → `BUILDER_REVISION_PROMPT`: "This is a revision. Preserve valid work. Address the Guardian feedback. Do not introduce unrelated changes. Produce the same schema", with the architecture/research summary, the previous task graph (compact rendering), the feedback, the requested changes and the revision number. Same `LLMTaskGraph` schema and the same validators. It skips Builder's "analysis" LLM call. No memories or event histories are injected (Queen memory is untouched).

## Guardian re-review

Guardian previously saw only `task_graph.summary`, so a revised task list would have been invisible to it. It now receives the task list itself (titles, dependencies, descriptions, acceptance criteria). For revision N it also gets a re-review context ("verify each previously requested change was addressed"). It reviews exactly the `task_graph` inside the `tasks.generated` event it consumes; the scheduler additionally ignores any event whose `revision_number` is lower than the run's current revision (stale) and fails the run if it is higher (state inconsistent).

## Idempotency and failure behavior

- Redelivered `review.completed` / `revision.requested` / terminal events are skipped by the events-table event-id check (Phase 1 mechanism, unchanged). A crash after publishing but before the commit re-derives the same child `event_id` and the same `revision_id`; revision inserts are `ON CONFLICT DO NOTHING`, plus the UNIQUE constraint.
- Builder or Guardian failing during a revision → `run.failed` (`failed_stage` builder/guardian) and the pending revision row becomes `failed`. `revision.requested` publish failure → `run.failed`, and no revision row/task is committed (the DB effects were never applied). No retry storm: failures are recorded and the offset is committed, as in Phase 1.
- Bug found and fixed during testing (would have broken every live revision): the revision prompt's `{feedback}` variable collided with the retry helper's own `feedback` parameter; the helper's parameter is now `retry_feedback`.

## Automated tests

`cd backend && pytest -q`: **156 passed, 0 failed, 0 skipped** (was 117). `alembic check`: clean; fresh chain of 5 migrations up/down/up verified.
- `tests/test_revision.py` (37, fake agents + real PostgreSQL): revision payload validation; deterministic ids; feedback extraction; numbering; **approved first review** (one review, no revision), **one revision**, **multiple revisions**, **revision limit** (`MAX_REVISIONS=2`: exactly 2 Builder revisions, no 4th run, failure payload keeps feedback), `MAX_REVISIONS=0`, **rejected**, rejected during a revision; run never `completed` while a revision is pending; invalid Guardian output; duplicate `review.completed` → one request/one row; duplicate `revision.requested` → Builder once (both mid-run and after completion); duplicate terminal event; crash-before-commit re-derives the same identities; stale and ahead-of-state events; Builder failure and Guardian failure during a revision; `revision.requested` publish failure; DB unique/CHECK constraints; the **real Builder and Guardian workflows with a scripted LLM** (revision prompt carries feedback + previous tasks + rules; Guardian sees the task list and gets re-review context; first-pass Builder unchanged).
- `tests/test_e2e_kafka.py` (+3, real Kafka): revision loop completes; **scheduler hard-crashed (SystemExit) while processing `revision.requested`, restarted with the same consumer group** → Kafka redelivers, Builder revision completes exactly once (2 attempts, 1 completion), 1 revision row, no duplicate tasks (`{0: 2, 1: 3}`), 10 unique events, Guardian reviews revision 1's output; revision limit (`MAX_REVISIONS=1`) → `run.failed MAX_REVISIONS_EXCEEDED`.
- The Phase 1 test that expected `needs_revision` → `ReviewNeedsRevision` now covers `rejected` only (that behavior was intentionally replaced). All Phase 1/2 tests otherwise unchanged and passing (memory tests included).

## Live E2E (real stack: Groq gpt-oss-120b, local bge-small, PostgreSQL/pgvector, Kafka, FastAPI, Scheduler; no model overrides, no fake agents, no DB manipulation)

| Scenario | Result | Run |
|---|---|---|
| **A — approved first time** | **VERIFIED**: `completed`, 0 revisions, 5 tasks, 93.0 s | `eee6b7a6-f96e-41bf-a16b-74b18493ba6e` |
| **B — revision path** | **VERIFIED** (Guardian's own verdict): `completed`, 1 revision, 151.1 s | `63a05abf-48a2-486f-9f88-6fee1daa0ddc` |
| **C — revision limit** | **NOT VERIFIED live** (see below); verified by automated tests incl. real Kafka | — |

**A** events: `run.created → strategy.created → architecture.created → research.completed → tasks.generated(rev 0) → review.completed(approved) → run.completed`.

**B** (goal "Design the data storage layer and the user interface technology for the expense tracker monthly reports feature."): `… research.completed → tasks.generated(rev 0, 7 tasks) → review.completed(needs_revision) → revision.requested(rev 1) → tasks.generated(rev 1, 11 tasks) → review.completed(approved) → run.completed`. `run_revisions`: one row, `approved`, with the source review, Builder output event and re-review event ids recorded; Guardian's feedback (security, performance) and 6 requested changes (authentication/authorization, input validation, indexing, rate limiting/logging, aggregation-job failure handling, UI security). Builder kept all 7 original tasks and added 4 tasks that map to the requests (indexing/query guidelines, aggregation scheduling/failure handling, UI security, secure API layer). Guardian's reviewed graph had 7 tasks in review 0 and 11 tasks in review 1 (it re-reviewed the new task set). `/workflow/{id}/status`: `completed`, `revision_count=1`, `revision_status=approved`.

**C — why not verified live:** with `MAX_REVISIONS=1` (env override on the API and Scheduler processes only, `.env` untouched, since stopped), five real runs were tried and none produced two consecutive `needs_revision` verdicts:
- payment-processing plan, the monthly-reports goal again, and a vague "make the expense tracker better" goal: Guardian **approved on the first review** each time (`completed`, 0 revisions). Since Guardian now sees the task list it approves much more readily (4 of 5 first reviews approved; earlier, when it saw only a summary, 3 of 5 live first reviews were `needs_revision`).
- a contradictory-requirements goal: the run failed at Guardian with Groq **429 TPD** (daily token limit) after the client's retries (`run.failed`, `failed_stage=guardian`).
- a deliberately harmful goal: `gpt-oss` refused to produce JSON at Queen after 2 attempts → `run.failed` (`failed_stage=queen`).
The Groq free-tier daily limit (200,000 tokens/day, rolling 24 h) was then exhausted (198,026 used), so no further live attempt was possible. Nothing was faked. The limit path is covered by the automated tests above (real PostgreSQL; and real Kafka with fake agents).

## Remaining limitations

- Live revision-limit path unverified (Groq daily token limit); live approved and revision paths were each verified once.
- Guardian is lenient when it sees the full task list; natural `needs_revision` is now uncommon, and the loop's quality depends on Guardian's feedback being actionable.
- The loop revises only the Builder's task graph; Architect/Scout outputs are never revised, and there is no deduplication of feedback across revisions or detection of a "no-op" revision (identical graph).
- `rejected` is terminal (no recovery). A stuck or redelivery-interrupted run can still be replayed by the same at-least-once rules as Phase 1; there is no run cancellation.
- Groq free-tier limits (TPM/TPD) still cause 429 backoffs and can fail runs (seen live); each revision adds two LLM calls (Builder + Guardian).
- Frontend does not display revisions (API only); `revisions` in the status payload exposes them.

---

# Phase 4 — Real-Time WebSocket Telemetry

Date: 2026-09-24. Replaces the frontend replay/simulation (`useEventStream`) with a real WebSocket pipeline. Supersedes the Phase 0 findings "WebSockets: missing" and "EventFeed shows recycled historical events as live".

## Audit (before changes)

- The only "stream" was `frontend/hooks/useEventStream.ts` (used by the dashboard `EventFeed`): fetch `/events/recent` once, then a timer replays the old events every 3-6 s with fresh timestamps. No WebSocket/SSE existed in the backend or anywhere else.
- Kafka events are consumed and persisted **in the Scheduler process** (`app/scheduler/consumer.py`, event row + effects committed, then offset), while browsers talk to the **FastAPI process**. The hub therefore has to live in the API process and be fed by something the Scheduler does after its commit.

## Architecture

```
Kafka -> Scheduler -> PostgreSQL (events, runs, tasks, run_revisions) -- COMMIT --> pg_notify('hivemind_events', run_id)
                                                                                         |
FastAPI process: LISTEN thread -> TelemetryHub (run_id -> clients, bounded queue each) -> ws://host/ws/runs/{run_id}
                                                                                         |
                                                                                    Next.js dashboard
```
- **Kafka/PostgreSQL = source of truth, WebSocket = observational, frontend = cache.** The Scheduler never calls the hub and does not know browsers exist. It only runs `pg_notify` best-effort **after** its commit (`SchedulerConsumer._notify_committed`: a failure is logged and ignored). Broadcast is therefore always after persistence, is never a prerequisite for the offset commit, and cannot fail/roll back/stall a run.
- **Delivery by cursor.** Each client has a cursor (`(created_at, id)` of the last event it received; the same order as `get_events_by_run`). A notification (or the 5 s safety poll, or the LISTEN reconnect catch-up) makes every client of that run read "events after my cursor" from PostgreSQL. Snapshot, missed-event recovery and live delivery are the same query, so they cannot disagree, gap or duplicate; a lost NOTIFY only delays an update. No in-memory history buffer exists.
- The LISTEN connection runs in a dedicated thread with synchronous psycopg and hands work to the event loop with `call_soon_threadsafe` (psycopg's async mode cannot use the `ProactorEventLoop` that uvicorn uses on Windows).

## Endpoint and contract (`app/api/ws.py`, `app/telemetry/contract.py`)

`ws://host/ws/runs/{run_id}[?last_event_id=<event_id>]`. Messages (JSON objects with `type`):
- `workflow.snapshot` (first message on every connection): `{mode: "full"|"resume", run_id, state, events[], last_event_id}`. `full` = whole history (new page, refresh, unknown cursor); `resume` = only the events after `last_event_id`.
- `workflow.event`: `{event_id, event_type, run_id, timestamp, source, revision_number, payload}`; `event_id` is the dedup key. `payload` is a compact summary (counts, verdict, short summary, revision feedback preview), never the raw Kafka payload, prompts, model output or memory content; text is truncated, secret-scrubbed, and provider account/request ids (`org_…`, `req_…`) are redacted.
- `workflow.state`: authoritative run + per-agent state after each batch.
- `heartbeat` every 20 s; client `{"type":"ping"}` → `pong`.
- Close codes: 1008 origin rejected (handshake), 4400 malformed id, 4404 unknown run, 1013 slow consumer.
- **One definition of state:** `app/services/workflow_service.py::build_workflow_status` is used by both REST `/workflow/{id}/status` (now also returns `agents` and `last_event_id`) and the WebSocket snapshot/state messages.
- **Agent state reading (bug found and fixed during live testing):** the Scheduler persists an event only after the handler that *consumed* it finished, so a persisted event means "its consumer is done and the next agent is running now" (`run.created` → Queen done / Architect running; … `research.completed` → Builder done / Guardian running; `review.completed(needs_revision)` → Builder running revision n+1; `revision.requested` → Builder done / Guardian re-reviewing). The first implementation read events naively and showed each stage "running" one handler late; a live run exposed it, the mapping was corrected in the shared function and verified against a REST timeline.
- **Known consequence:** an event becomes visible when its consumption completes, so the event *log* trails the true frontier by one handler (e.g. `strategy.created` appears when the Architect finishes). Agent states are accurate; the log rows carry the event's real creation timestamp.

## Connection manager (`app/telemetry/hub.py`)

`connect / disconnect / subscribe / unsubscribe / notify_run / broadcast_to_run / broadcast / close_all`. `run_id → clients`; run A's events never reach run B's clients (tested and observed live via wire frames). Clients register **before** the snapshot is built and are `ready` only after it is queued, so nothing committed in between is missed. Every public method catches and logs its own errors.

## Backpressure and heartbeat

Each client has a bounded outgoing queue (100) and its own sender task with a 5 s send timeout. A slow or stalled browser can only fill its own queue: on overflow/timeout it is dropped (1013 / closed) and recovers from PostgreSQL by reconnecting; healthy clients and the Scheduler are unaffected (tested with a stalled fake socket beside a healthy one). Heartbeats every 20 s; the frontend watchdog treats 50 s of silence as a dead link.

## Security boundary

Browsers do not apply CORS to WebSockets, so the endpoint checks `Origin` against `CORS_ORIGINS` (non-browser clients send none; a foreign origin is rejected during the handshake). Run and event ids are validated (`[A-Za-z0-9_-]{1,64}`) before any query (tested: the database is not touched for malformed ids). **Authentication/authorization is not implemented**: `app.api.ws.authorize` is the single integration point for a future phase; today anyone who can reach the API and knows a run id can watch it.

## Frontend

- `hooks/useEventStream.ts` (rewritten): `useEventStream({runId, enabled}) → {events, state, connectionState, error, nextRetryMs, reconnect, lastEvent, isTerminal}`. `connectionState` ∈ connecting | connected | reconnecting | disconnected | error and describes the **transport only**; workflow failure comes only from `run.failed` / `state.status`.
- `lib/telemetry/client.ts`: reconnecting client: bounded exponential backoff with jitter (1 s, 2 s, 4 s … 30 s cap; reset after a snapshot proves a round trip), resume with `?last_event_id=` of the last applied event, `online` event reconnects immediately, stale-link watchdog, no retry for 1008/4400/4404 (shown as an error with a Reconnect button), no retry after the workflow is terminal. Found while testing over real sockets: Node's built-in WebSocket never fires `close` for a refused connection, so an `error` with no close is now treated as a failed connection.
- `lib/telemetry/reducer.ts`: pure, dedup by `event_id`; `full` snapshot replaces, `resume` appends only new events.
- UI: `LiveRunPanel` (agent pipeline Queen → Architect → Scout → Builder → Guardian with pending/running/completed/failed/revision, revision timeline "Guardian needs revision → Revision N (feedback and requested-change counts) → Builder produced N tasks → Guardian approved", terminal banners with a safe failure summary, connection badge, "live updates paused, the run continues on the server" note), `LiveRunSection` (run picker + `/workflow?run=<id>` deep link) on the Workflow page, and the dashboard `EventFeed` now streams the latest run over the WebSocket. Simulation code is removed (only comments mention it). `NEXT_PUBLIC_API_ORIGIN` / `NEXT_PUBLIC_WS_ORIGIN` configure endpoints (`lib/config.ts`; `lib/api.ts` uses the same base).
- `/health/` now also reports `websocket_clients` and per-run counts (used to verify cleanup).

## Automated tests

- Backend `pytest -q`: **194 passed, 0 failed, 0 skipped** (was 156; +38): `tests/test_telemetry.py` (36) against real PostgreSQL through the real Scheduler → NOTIFY → listener thread → hub → TestClient sockets: connect/disconnect cleanup, unknown run (4404), malformed ids (4400, no DB access), origin check, ping/pong, heartbeat, live events in order and only after commit, run isolation and two tabs, hub bookkeeping, snapshot == REST, missed-event recovery (resume), resume-then-live, unknown/foreign `last_event_id`, revision and failure telemetry, safe failure payloads, payloads are summaries, provider-id scrubbing, failure isolation (NOTIFY failing after every commit; hub raising; browser closing mid-run; no WebSocket infrastructure at all), backpressure with fake sockets (slow client dropped and never blocks a healthy one; stalled socket timeout; recovery from the DB), cursor ordering/scoping. `tests/test_e2e_kafka.py` (+3, **real Kafka + PostgreSQL**, fake agents with a delay so events happen while the client is away): Kafka → DB → WebSocket after persistence; disconnect → events occur → reconnect → missed events recovered with no duplicates; revision run visible over the socket.
- Frontend `npm test` (vitest): **59 passed**: reducer (9), view helpers/revision timeline (6), client with fake sockets and fake timers (17: states, backoff values and cap, resume URL, manual reconnect, non-retryable codes, terminal, 1013, watchdog, malformed frames, stale sockets), hook (11), `LiveRunPanel` (10: agent cards follow backend state not timers, dedup, revision visualisation, completed/failed banners with safe text, a dropped connection never looks like a failed workflow, recovery, refresh, unknown run), and **6 tests against real `ws` sockets** (abrupt drops, several consecutive drops, server down with 40/80/160 ms backoff then recovery, 4404, watchdog, full-snapshot replacement). `tsc` clean; `npm run build` passes (all 9 routes prerender, `/workflow` uses a Suspense boundary for `useSearchParams`); eslint clean on all new/changed files (pre-existing lint errors elsewhere untouched).

## Live verification

Stack: docker compose PostgreSQL+pgvector and Kafka, **real uvicorn API, real scheduler process, real Next.js production server, real Chromium (Playwright, headless)**, real WebSocket frames recorded in the browser. **Because the Groq daily token limit was exhausted (see below), the agents in the scheduler process were deterministic fakes** (`tests/live_fake_scheduler.py`: real Kafka consumer, real PostgreSQL commits, real notifications; per-agent delay 2.5 s; the goal text selects revise/fail behaviour). This verifies the whole telemetry path; it does not verify LLM-driven runs.

| Live test | Result | Run | Sequence / final |
|---|---|---|---|
| Normal run | **VERIFIED** (10/10 checks) | `996913b3-21b2-4fea-8ffd-4361f9e54bab` | all five agents seen running live in order, 7 events over the socket (7 live frames), completed, REST agrees |
| Revision run | **VERIFIED** (8/8) | `0a947d55-3fa7-4834-83c2-82924ce92ffa` | `… review(needs_revision) → revision.requested → tasks.generated → review(approved) → run.completed`; Guardian shown "revision", Builder running again, timeline "Revision 1 of 3 … approved", banner "Run completed after 1 revision" |
| Failed run | **VERIFIED** (4/4) | `b3eb8aa0-f07c-486d-a206-710a19ecd9ba` | failed at scout with a safe message, later agents pending, socket still connected |
| Disconnect + recovery | **VERIFIED** (14/14) | `3a8063c9-72de-420b-a777-a460b203d3f3` | WebSocket cut mid-run and blocked ~12 s: UI "Reconnecting…, live updates paused", not failed; server finished the run meanwhile (7 events vs 2 shown); reconnect attempts at 0.9 s, 2.9 s, 7.3 s (backoff); after the network returned the browser asked with `last_event_id`, got a `resume` snapshot with only the 5 missed events; final UI == durable history, 7 rows, no duplicates, completed |
| Browser refresh mid-run | **VERIFIED** (5/5) | `0ed303df-5519-413f-826b-0468c22eff24` | state rebuilt from a full snapshot, run not restarted (one `run.created`), 7 events, no duplicates |
| Multiple clients | **VERIFIED** (7/7) | A `63dcd5f6-7606-46ec-9784-91d24a5e9570` ×2 tabs, B `bb541df1-576e-415c-bdc2-bfc9cb95d1ab` | hub saw 2 clients for A and 1 for B; both A tabs got the full history; B's frames only ever carried B's run id; event ids disjoint; after closing the tabs the hub had 0 clients (real uvicorn disconnect handling) |
| Real LLM (Groq) run through the UI | **NOT VERIFIED end to end** | `d8fd4de6-5cc4-4bac-b853-b432d7965060` | Queen and Architect ran on real Groq and streamed live into the browser (`queen running → completed → architect running → completed`), then Scout failed with Groq 429 (daily token limit exhausted, 200,000 tokens/day rolling window used up by earlier phases): the browser showed "Run failed at scout" with the sanitised error, and (before the fix below) the provider's organisation id, which is now redacted |

Screenshots of the normal, revision, failed, disconnected, recovered and multi-tab views were captured and inspected. Live testing found and fixed: the one-handler-late agent state reading, the provider id shown in a failure message, and the Node WebSocket no-`close` quirk.

## Remaining limitations

- **No end-to-end live run with the real LLM** through the WebSocket UI (Groq daily token limit). Real-LLM telemetry was seen for two stages only. Not verified: the real Guardian revision path in the UI.
- The event log trails the true frontier by one handler (events are persisted after their consumer finishes); agent states are accurate.
- Delivery is per API process: with several API instances each has its own hub and listener (works, since all read PostgreSQL), but there is no cross-instance connection registry; `pg_notify` + polling scale to modest client counts, not thousands.
- No authentication or per-user authorization (Origin check only). Anyone with a run id and an allowed origin/non-browser client can watch that run.
- The UI does not chart revision history beyond the timeline; the Runs page drawer still uses REST only. Agent names on other pages still use the legacy role keys.
- Frontend lint still has pre-existing errors in files not touched here. TestClient does not deliver disconnects the way uvicorn does, so disconnect cleanup is verified live (uvicorn), and tests close sockets explicitly.


---

# Phase 5 — Testing & Reliability Hardening

Goal: prove the pipeline stays correct under crashes, restarts, duplicate delivery, disconnects, provider limits and database/network problems, without adding product features. Every guarantee below is backed by a test that fails if the guarantee breaks (the invariant checker itself is tested against deliberately corrupted databases).

## Reliability matrix

| # | Failure | Expected | Actual (after Phase 5) | Test |
|---|---------|----------|------------------------|------|
| 1 | Scheduler crash before publishing the child event | agent re-runs once on restart, run completes | OK | `test_reliability_kafka::test_crash_matrix_approved_path[before_publish-*]` |
| 2 | Crash after publishing, before DB commit | duplicate child is harmless (deterministic id + PK dedup) | OK | `[after_publish-*]`, revision-path matrix |
| 3 | Crash right before DB COMMIT | nothing persisted (event row + tasks/revision are one txn), redelivered | OK | `[at_commit-*]`, `test_reliability_db::test_result_and_event_row_are_one_transaction` |
| 4 | Crash after DB commit, before offset commit | redelivery is a no-op; agent NOT re-run | OK | `[after_db_commit-*]` (agent executed exactly once) |
| 5 | Several crashes in one run / during MAX_REVISIONS | converges, bound never exceeded | OK | `test_multiple_crashes_in_one_run`, `test_max_revisions_is_not_exceeded_across_crashes_and_restarts` |
| 6 | Every event delivered twice / replay after completion | each agent once, one `run.completed` | OK | `test_duplicate_delivery_*` |
| 7 | Two workers race on one event | one row wins, the other is a duplicate skip (not a poison event) | OK (fixed) | `test_concurrent_workers_on_the_same_event...` |
| 8 | Kafka publish of the child event fails | retry the message; run is NOT failed | OK (fixed: it used to fail healthy runs) | `test_publish_failure_is_retried_not_lost` |
| 9 | Consumer poll error / offset-commit failure | loop survives; redelivery is idempotent | OK | `test_consumer_poll_errors...`, `test_offset_commit_failure...` |
| 10 | Transient DB error (connection reset) | message retried, run kept, not an agent failure | OK (fixed: was mis-classified) | `test_transient_db_error_is_retried...` |
| 11 | Permanent DB error (10 tasks, 7th unstorable) | no partial tasks, run failed, consumer not blocked | OK (fixed: was an infinite retry) | `test_permanent_db_error_rolls_back_all_tasks...` |
| 12 | Even the failure record cannot be stored | event skipped, CRITICAL log, queue keeps moving | OK | `test_unrecordable_poison_event_is_skipped...` |
| 13 | Agent raises / times out at each stage | run `failed` once with the right `failed_stage`, agent not silently re-run | OK | `test_reliability_agents` (10 cases) |
| 14 | Guardian returns an unknown verdict | run fails; no revision loop | OK (fixed: was looping) | `test_unknown_guardian_verdict_fails_instead_of_looping` |
| 15 | Guardian always `needs_revision` | stops at MAX_REVISIONS with `MAX_REVISIONS_EXCEEDED` | OK | `test_always_needs_revision_stops_at_max_revisions` |
| 16 | Kafka down at `POST /runs` | HTTP 503 + run recorded as `failed` | OK | `test_scheduler` (503 assertion) |
| 17 | Embedding provider hangs | `EmbeddingError` after `EMBEDDING_TIMEOUT_S` | OK (new timeout) | `test_reliability_memory::test_a_hung_embedding_provider...` |
| 18 | DB error during memory retrieval | explicit failure, never "no memories" | OK | `test_database_failure_during_retrieval...` |
| 19 | NOTIFY lost / LISTEN connection killed | WS catches up via safety poll / reconnect; DB is truth | OK | `test_reliability_ws` |
| 20 | REST vs WS vs DB at running/completed/failed/revision-pending | identical state | OK | `test_rest_ws_and_db_agree_at_each_state` |
| 21 | Duplicate / out-of-order WS events in the browser | timeline stays chronological, no duplicates | OK (reducer now inserts by timestamp) | `lib/telemetry/reliability.test.ts` |
| 22 | Scheduler process dies at each stage on real Kafka | restart in the same group completes the run once | OK | `test_reliability_restart` (6 stages) |
| 23 | 10 concurrent runs / 50 seeded runs with random crashes + duplicates | all terminal, invariants clean, isolation kept | OK (seeds 20260924, 1, 2, 3) | `test_reliability_stress` |
| 24 | Secrets in logs | scrubbed (message + traceback), UUIDs kept | OK | `test_reliability_observability` |

## Defects found and fixed in Phase 5

1. Unknown Guardian verdict (e.g. "maybe") entered the revision loop. `overall_verdict` is now a `Literal`, and a `review.completed` with an unrecognised verdict fails the run.
2. A permanently failing DB write retried forever, blocking the consumer and leaving the run `running`. Poison-event isolation now fails that run directly in PostgreSQL and commits the offset.
3. Transient DB errors were recorded as agent failures. They are now classified as infrastructure and retried.
4. A Kafka publish failure failed the run (found by the crash-matrix work). Publishing is now infrastructure: nothing is persisted and the message is retried. Two older tests that asserted the previous behaviour were updated to the new contract.
5. Provider errors could echo API keys into logs. `SecretRedactingFilter` is installed on every root handler (API and Scheduler).
6. A concurrent duplicate PK insert would have failed a healthy run. It is now detected via `event_exists` and treated as a duplicate.
7. `POST /runs` with Kafka down raised a raw 500. It now returns 503 and marks the run failed.
8. Embedding calls had no timeout. `EMBEDDING_TIMEOUT_S` (30 s) now applies.
9. Run status accepted any string on update. It is now validated (`running|completed|failed`).

## Error taxonomy (scheduler)

| Class | Examples | Handling |
|-------|----------|----------|
| Agent/handler error | agent exception, timeout, schema violation, bad verdict | run -> `failed` (`failed_stage`, `error_type`), offset committed, never re-run |
| Infrastructure, transient | DB connection reset, Kafka publish/commit error | offset NOT committed; message retried after `RETRY_PAUSE_S` (`stop()` interrupts the pause) |
| Persistence, permanent | constraint / data error on save | rollback, run failed directly in DB, offset committed (`poison_events`) |
| Duplicate / stale | already-persisted event, terminal run, superseded revision | ignored, offset committed |

## Stale-run policy

HiveMind never auto-fails a long-running run (LLM calls, backlogs and rate limits legitimately take minutes). Stale runs (no event for `STALE_RUN_MINUTES`, default 30) are only reported: `GET /api/v1/workflow/stale`, `idle_seconds`/`stale` on the workflow status, and a read-only warning when the Scheduler starts. An operator decides.

## Observability

- Every scheduler/memory log line carries `run=` and `event=` (plus `rev=`); secrets are redacted.
- `app/core/metrics.py` counters/timers: events processed/duplicate/ignored, runs started/completed/failed, agent failures per stage, revisions requested, revision-limit failures, poison events, infra retries, agent latency, embedding/memory latency, embedding timeouts, websocket connections/reconnects/slow-client drops. The Scheduler logs a `metrics {...}` snapshot every 60 s and on shutdown.
- `GET /health/metrics`: DB-derived totals (runs by status, failures by stage/error, revisions, average duration) plus API-process counters.

## Test tooling added

`tests/minikafka.py` (deterministic in-memory Kafka driving the REAL `SchedulerConsumer.start()`; crash points `before_publish`, `after_publish`, `at_commit`, `after_db_commit`; poll/commit/publish faults), `tests/scenario_agents.py` (goal-driven agents so concurrent runs behave differently), `tests/invariants.py` (11 database invariants, self-tested for corruption detection).

## Memory recall measurement (real `bge-small-en-v1.5`, `MEMORY_MIN_SIMILARITY=0.60`, unchanged)

5 paraphrase queries over 5 memories: recall@3 4/5, top-1 4/5; 0/2 unrelated queries returned anything. The one miss ("Which language model provider do we call?" vs the Groq memory) scores below 0.60. The threshold was deliberately not lowered; it is a precision/recall trade-off to revisit with real data.

## Live Groq verification

Quota probe: 200 OK, but the tier allows 8,000 tokens/minute, which a full five-agent run exceeds. Verified live: one Queen strategy call through the real client (5.3 s, valid structured output). NOT VERIFIED live: a full Queen-to-Guardian run and the live 429 path (covered only by deterministic tests).

## Remaining limitations

- Frontend lint still reports 5 errors in files not touched by HiveMind work (`AgentCard`, `AgentDetailPanel`, `chart-area-interactive`, `use-mobile`, `useApi`); 5 more (in `lib/api.ts` / `types/index.ts`) were fixed.
- The scheduler retries an infrastructure error indefinitely (with a pause), by design: dropping the message would lose a run. A permanently broken broker therefore stalls processing visibly (logged, `infra_retries`) rather than failing runs.
- `backend/test_queen.py` (a manual live script) is stale (pre-Phase-2 constructor) and was not part of this phase.
- Stress uses fake agents; latency and throughput under real LLM load are not measured.
- No authentication, no deployment work (out of scope by design).


---

# Phase 6 — Multi-Provider LLM Architecture

Agents depend on a stable internal LLM interface; providers implement it. Switching provider is configuration only.

## Audit (before the change)

| Topic | Finding |
|-------|---------|
| Architecture | `get_llm()` returned a LlamaIndex `Groq` object; five `*Service` classes injected it into their LlamaIndex workflows. |
| Coupling points | Workflows typed `llm: llama_index.core.llms.LLM` and called `llm.acomplete(...)` directly (Architect, Builder, Guardian, Scout analysis step); `agents/base/structured.py` sent Groq-style `response_format` JSON mode; config required `GROQ_API_KEY`; redaction and the scheduler scrubber only knew the Groq key; `system_service` hard-coded "Groq". |
| Retry behaviour | Three layers: OpenAI-SDK transport retries (429 Retry-After, 5xx; default 3), `with_retry` (2 attempts, retried EVERY exception including auth errors), scheduler (never re-runs a failed agent; retries only DB/Kafka). |
| Structured output | Schema-in-prompt + JSON mode + JSON extraction + Pydantic (`StructuredOutputError`), because LlamaIndex function-calling fails on gpt-oss. |
| Test coverage | `test_llm_groq.py` asserted "Groq only, no Featherless anywhere" (obsolete by design); `ScriptedLLM` faked `acomplete`. |
| Risks | Featherless `response_format` support unverified; nested retries; error types leaking SDK classes. |

## Architecture

```
Agents (Queen / Architect / Scout / Builder / Guardian)
  -> HiveMind LLM interface   agents/llm/interface.py   LLMClient.complete / structured_output
  -> Provider factory         agents/llm/factory.py     settings.LLM_PROVIDER -> adapter (validated at startup)
  -> Provider adapter         groq_client.py | featherless_client.py   (transport only)
  -> External LLM
```

- **Interface:** `complete(prompt, json_mode=False) -> str` and `structured_output(output_cls, prompt, retry_feedback=None) -> T`. Adapters implement only `_complete`. Error normalisation, empty-response handling and the whole structured-output pipeline live in the base class, so every provider behaves identically and agents keep receiving validated Pydantic models.
- **Providers:** `groq` (default; LlamaIndex `Groq`, `reasoning_effort` kept) and `featherless` (OpenAI-compatible API through LlamaIndex `OpenAILike`, base URL `FEATHERLESS_BASE_URL`).
- **Configuration:** `LLM_PROVIDER`, `LLM_MODEL` (empty = provider default; Groq -> `openai/gpt-oss-120b`; Featherless has no default and requires it), `GROQ_API_KEY`, `FEATHERLESS_API_KEY`, `LLM_REQUEST_TIMEOUT_S` (120), `LLM_MAX_RETRIES` (3). Only the selected provider's key is required. `log_llm_config()` validates at API and Scheduler startup and raises `LLMConfigError` with an actionable message (never a secret).
- **Structured output:** one path for all providers: schema in the prompt -> JSON extraction -> Pydantic validation. Groq additionally gets `response_format=json_object`; Featherless does not (per-model support is unverified). Unusable output (empty, prose, wrong type, missing field, invalid enum/verdict) is `LLMInvalidResponseError`.
- **Errors (`agents/llm/errors.py`):** `LLMError(GenerationError)` -> `LLMTimeoutError`, `LLMRateLimitError` (keeps `retry_after`), `LLMAuthenticationError` (401/403), `LLMProviderError` (5xx/4xx/connection), `LLMInvalidResponseError`. Messages are redacted with the Phase 5 filter. Because they are `GenerationError`s, the scheduler records them exactly like before: run `failed`, `error_type` = the neutral class name, agent not re-run.

## Retry ownership (no multiplication)

| Layer | Owns | Bound |
|-------|------|-------|
| Provider SDK | transport retries inside ONE call (429 with Retry-After, 5xx, connection) | `LLM_MAX_RETRIES` (3) |
| `with_retry` | ONLY `LLMInvalidResponseError`, re-asking with the failure as feedback | 2 attempts |
| Scheduler | never re-runs a failed agent; retries only DB/Kafka infrastructure errors | Phase 5 contract |

Decision: `with_retry` previously retried every exception, so an auth error or a 429 that the SDK had already retried was sent again (2 x 4 HTTP calls). It now retries only unusable output; transport errors propagate immediately as neutral errors. Worst case per LLM call: 2 attempts x (1 + 3 SDK retries) = 8 HTTP calls, and only when the model keeps returning garbage.

## Fake provider and tests

`agents/llm/fake.py` `FakeLLM` (scripted replies; injectable `timeout | rate_limit | auth | provider_error | raw_timeout`) goes through the same base-class pipeline. `tests/test_llm_providers.py` (61 tests): configuration/factory, both real adapters against a local OpenAI-compatible HTTP server (200, 429 with Retry-After, 401, 403, 500, 400, timeout, malformed / missing-field / wrong-type output), retry ownership (transport errors called once, not 5 times), all five agents on each provider and on a swapped-in implementation, invalid Guardian verdicts, neutral errors through the scheduler (`test_reliability_agents`), and architectural enforcement.

## Enforcement (static tests)

No module under `agents/` or `app/` outside the adapters/factory/error mapping may import `llama_index.llms*`, `openai`, `groq`, `httpx` or a provider module; provider credential names appear only in config, redaction, factory and adapters; agent code (outside `agents/llm/`) never names a provider. Classified findings: adapters, factory, `errors.py`, `config.py`, `redaction.py` = ALLOWED; agent workflows, scheduler, services = clean.

## Security

Keys are read only by adapters; startup logs, error messages (`redact_secrets`, now including the Featherless key) and API responses never contain them; `.env` is git-ignored and `.env.example` holds placeholders (both asserted by tests); the frontend never receives a key (secret-pattern scan clean; the settings pages use mock data only).

## Live verification

| | Result |
|-|--------|
| Implemented and deterministically tested | YES |
| Groq through the new interface | VERIFIED live (`structured_output` returned a valid model, `openai/gpt-oss-120b`, 2.3 s) |
| Featherless | NOT live-verified: no `FEATHERLESS_API_KEY` in this environment. Adapter verified only against a local OpenAI-compatible server. |

## Limitations

- Featherless model availability, `response_format` support and real rate-limit behaviour are unverified; `LLM_MODEL` has no default there.
- One provider and model for all agents (no per-agent routing, no fallback between providers, by design).
- A full live 5-agent run is still not verified (Groq 8,000 TPM tier).
- `backend/test_llm.py` and `backend/test_queen.py` are manual live scripts outside the suite (the latter is stale since Phase 2); `agents/queen/agent_old.py` and `agents/llm/base.py` (old `BaseLLM`) are dead code left untouched.
- `LLM_MODEL` default changed from `openai/gpt-oss-120b` to empty (= provider default) so a second provider needs no Groq model name; existing `.env` files that set it are unaffected.
