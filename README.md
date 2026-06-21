<p align="center">
  <strong>🐝 HiveMind</strong>
  <br />
  <em>An Autonomous Multi-Agent Operating System</em>
</p>

<p align="center">
  One goal · Multiple specialized agents · Shared intelligence
</p>

---

HiveMind is an AI-native operating system where autonomous agents collaborate to plan, research, execute, review, and learn from complex objectives — without human intervention at each step.

Instead of interacting with a single AI assistant, a user provides a high-level goal and HiveMind coordinates a digital workforce of specialized agents to accomplish it end-to-end.

> **This is not a chatbot.** This is not a CRUD dashboard. This is not a single-agent wrapper.
> HiveMind explores a fundamentally different paradigm: **AI as an organization.**

---

## Vision

A user provides an objective:

```
Build a marketing website for a bakery.
```

HiveMind autonomously:

1. Creates a strategy and defines success criteria.
2. Decomposes work into a dependency-aware task graph.
3. Researches context via web search and prior knowledge.
4. Produces the deliverable, grounded in gathered context.
5. Reviews output against success criteria — rejects and retries if needed.
6. Stores knowledge for future runs.
7. Reports progress through a real-time dashboard.

The long-term goal is a platform combining **multi-agent systems**, **workflow orchestration**, **knowledge management**, **autonomous execution**, and **AI research infrastructure**.

---

## Core Philosophy

> AI systems should collaborate like teams, not behave like isolated assistants.

- Every agent has a dedicated role. No single agent solves everything.
- Agents never call each other directly — all communication flows through an event bus.
- Intelligence emerges through coordination, not individual capability.

---

## Architecture

```
                    User Goal
                        │
                        ▼
                    ┌────────┐
                    │ Queen  │   Strategy + Success Criteria
                    └───┬────┘
                        │
                        ▼
                   ┌──────────┐
                   │ Architect│   Task Graph + Dependencies
                   └────┬─────┘
                        │
                ┌───────┴───────┐
                ▼               ▼
          ┌──────────┐   ┌──────────┐
          │  Scout   │   │ Builder  │   Research ‖ Execution
          └────┬─────┘   └────┬─────┘
               │              │
               └──────┬───────┘
                      ▼
                 ┌──────────┐
                 │ Guardian │   Review + QA
                 └────┬─────┘
                      │  ↺ reject → Builder (capped retries)
                      ▼
               Store + Notify
```

All communication occurs through **Redis pub/sub** — a centralized event bus that promotes loose coupling, scalability, agent independence, and full observability.

---

## Agent Workforce

| Agent | Role | Responsibilities |
|-------|------|-----------------|
| **👑 Queen** | Strategic Planning | Interpret objectives, define measurable success criteria, create execution strategy |
| **🏗️ Architect** | Task Decomposition | Break plans into dependency-aware task graphs, manage execution order |
| **🔍 Scout** | Research & Context | Retrieve information via web search, gather external knowledge, write findings to memory |
| **🛠️ Builder** | Execution | Produce deliverables grounded in RAG context, implement solutions |
| **🛡️ Guardian** | Quality Assurance | Validate outputs against success criteria, request revisions with structured feedback |

Guardian is a merged Reviewer + QA role. Five agents exist in v1 — no more, no less.

---

## Memory System

HiveMind incorporates a long-term memory layer powered by **pgvector** (inside the primary PostgreSQL instance — no separate vector database).

```
Write Path                          Read Path
──────────                          ─────────
Agent Output                        New Task
     │                                   │
     ▼                                   ▼
  Chunking                          Embed Query
     │                                   │
     ▼                                   ▼
  Embedding                       Similarity Search
     │                                   │
     ▼                                   ▼
  pgvector                        Top-k Chunks → Inject into Prompt
```

Agents learn from previous executions and reuse organizational knowledge across runs.

---

## Event-Driven Design

Every action generates an event on the bus. The canonical event flow:

```
run_created → plan_ready → tasks_created → task_runnable
    → task_completed | task_rejected → task_approved → run_completed
```

The dashboard subscribes to the **same event stream** the agents use — it has no special access. This creates a fully transparent and observable execution pipeline.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15 · TypeScript · Tailwind CSS · shadcn/ui · Recharts |
| **Backend** | FastAPI · Python |
| **Database** | PostgreSQL + pgvector (single instance for relational data + vector memory) |
| **Messaging** | Redis (pub/sub + queues + cache — single Upstash instance) |
| **Infrastructure** | Docker · Docker Compose |
| **AI Providers** | Gemini (active default) · Claude · GPT · Ollama (local fallback) |

Design principle: **one LLM client, many roles** — agents share a provider, each with its own persona and system prompt.

---

## Roadmap

### v1 — Current

- [x] Queen, Architect, Scout, Builder, Guardian agents
- [x] Redis event bus (pub/sub)
- [x] PostgreSQL + pgvector memory
- [x] Real-time observability dashboard
- [x] `goal_to_deliverable` workflow template
- [x] Reject → retry loop (Guardian ↔ Builder)
- [x] Cost tracking in ₹ (INR)

### Future

- [ ] Memory Agent (dedicated knowledge management)
- [ ] Visual Workflow Builder
- [ ] Knowledge Graph integration
- [ ] Advanced RAG (hybrid search, re-ranking)
- [ ] Multi-Agent Debate
- [ ] Reflection Loops & ReAct experiments
- [ ] Tree of Thoughts
- [ ] LangGraph integration
- [ ] Prometheus + Grafana observability
- [ ] Kubernetes deployment

---

## Learning Objectives

This project is a long-term AI engineering laboratory focused on:

- Multi-Agent Systems & Orchestration
- RAG Architectures & Vector Search
- Event-Driven & Distributed Systems
- Workflow Automation
- System Design & Observability
- Reasoning Pattern Research (ReAct, Reflection, Tree of Thoughts)

---

## Project Goal

The purpose of HiveMind is not merely to build software — it is to understand how intelligent systems can be **organized**, **coordinated**, **observed**, and **continuously improved**.

HiveMind is designed to evolve over years, not weeks.

---

<p align="center">
  <em>One platform · Many agents · Shared intelligence</em>
</p>