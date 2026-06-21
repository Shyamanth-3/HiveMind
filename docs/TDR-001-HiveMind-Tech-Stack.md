# TDR-001: HiveMind V1 Technology Stack

## Status
Accepted


# Context

HiveMind is a long-term multi-agent operating system focused on AI Engineering, Agent Systems, RAG, Workflow Automation, Distributed Systems, and System Design.

Guiding principle:

> HiveMind is an event-driven system first and an AI system second.


# Frontend

## Selected

- Next.js 15
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query

## Why

- Better long-term architecture for a platform.
- File-based routing.
- Strong TypeScript support.
- Excellent authentication ecosystem.
- Faster development with reusable UI components.
- Scales naturally from dashboard to full platform.

---

# Backend

## Selected

- Python
- FastAPI

## Why

- Python-first AI ecosystem.
- Async support.
- Excellent WebSocket integration.
- High developer productivity.

---

# Primary Database

## Selected

- PostgreSQL

## Stores

- Projects
- Runs
- Tasks
- Events
- Agent Metadata
- Logs
- Memory Metadata

---

# Vector Memory

## Selected

- pgvector

## Architecture

PostgreSQL + pgvector

## Why

- Single database architecture.
- Low operational complexity.
- Easy migration path later.

## Deferred

- Qdrant
- Pinecone
- Weaviate
- Chroma

---

# Message Bus

## Selected

- Redis Pub/Sub

## Why

All agents communicate through events.

Example:

Queen → Architect → Scout → Builder → Guardian

Redis provides:

- Pub/Sub
- Queues
- Caching
- Low latency

## Future Upgrade

Redis → Kafka

---

# ORM & Migrations

## Selected

- SQLAlchemy
- Alembic

---

# Agent Framework

## Selected

- Custom Agent Framework

## Why

Learn:

- Agent orchestration
- Task routing
- Reflection loops
- Tool calling
- Event-driven coordination

## Deferred

- CrewAI
- AutoGen
- OpenAI Swarm

## Future

- LangGraph

---

# LLM Layer

## Architecture

Provider abstraction layer.

Supported providers:

- OpenAI
- Anthropic
- Gemini
- Ollama

Avoid vendor lock-in.

---

# Observability

## V1

- Structured Logging
- Loguru
- PostgreSQL log storage

Track:

- Latency
- Token usage
- Cost
- Success rate
- Failures

## Future

- Prometheus
- Grafana
- OpenTelemetry

---

# Authentication

## Selected

- JWT Authentication

---

# Real-Time Layer

## Selected

- FastAPI WebSockets

Enables:

- Live event streams
- Agent activity monitoring
- Dashboard updates

---

# Local Development

## Selected

- Docker
- Docker Compose

Services:

- Next.js
- FastAPI
- PostgreSQL
- Redis

Startup:

```bash
docker-compose up
```

---

# Infrastructure

## V1

- Docker
- Docker Compose

## Deferred

- Kubernetes
- Service Mesh
- Multi-region Deployment

---

# Testing

## Selected

- Pytest

Coverage:

- Agents
- Events
- APIs
- Memory
- Workflows

---

# Research Agent Tools

## Selected

- Tavily

## Alternative

- Serper

---

# File Storage

## V1

- Local Storage

## Future

- AWS S3
- Cloudflare R2

---

# Final HiveMind V1 Stack

## Frontend

- Next.js 15
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query

## Backend

- Python
- FastAPI

## Database

- PostgreSQL
- pgvector

## Messaging

- Redis Pub/Sub

## ORM

- SQLAlchemy
- Alembic

## AI Layer

- OpenAI
- Anthropic
- Gemini
- Ollama

## Agent System

- Custom Agent Framework

## Real-Time

- FastAPI WebSockets

## Infrastructure

- Docker
- Docker Compose

## Testing

- Pytest

## Research

- Tavily
