# HiveMind

HiveMind is a multi-agent operating system designed to coordinate autonomous AI agents through an event-driven architecture.

The platform enables specialized agents to plan, decompose, research, execute, review, and store knowledge while communicating through a centralized message bus.

---

## Technology Stack

### Frontend

* Next.js 15

### Backend

* Python
* FastAPI

### Database

* PostgreSQL
* pgvector

### Messaging

* Redis Pub/Sub

### Infrastructure

* Docker

### Testing

* Pytest

---

## Core Components

### Queen

Strategic planning and goal analysis.

Responsibilities:

* Goal understanding
* Strategy generation
* Success criteria definition

### Architect

Task decomposition and workflow generation.

Responsibilities:

* Task breakdown
* Dependency management
* Execution planning

### Scout

Research and context gathering.

Responsibilities:

* Information retrieval
* Context collection
* Knowledge enrichment

### Builder

Task execution and artifact generation.

Responsibilities:

* Deliverable creation
* Output generation
* Workflow execution

### Guardian

Quality assurance and validation.

Responsibilities:

* Output review
* Quality verification
* Revision requests

---

## System Architecture

Agents do not communicate directly.

All communication occurs through Redis events.

```text
Agent
  ↓
Redis Event
  ↓
Message Bus
  ↓
Next Agent
```

This architecture enables:

* Loose coupling
* Independent agent execution
* Horizontal scalability
* Future distributed deployment

---

## Memory Architecture

### Write Path

```text
Agent Output
    ↓
Chunk
    ↓
Embedding
    ↓
pgvector
```

### Read Path

```text
Query
    ↓
Embedding
    ↓
Similarity Search
    ↓
Retrieved Context
```


---

## Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
uvicorn app.main:app --reload
```

---

## License

This project is currently under active development.

---

## Maintainer

Nadella Shyamanth

