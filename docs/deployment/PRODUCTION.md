# HiveMind — Production Deployment

Target: **one Docker host running `docker-compose.prod.yml`**, with a TLS-terminating reverse proxy on the host. This
repository provides the hardened container configuration; it does **not** provision a host, DNS, certificates or the
reverse proxy. Nothing has been deployed to a public environment.

## Topology

```
Internet ──HTTPS/WSS──▶ reverse proxy (host: Caddy / nginx / cloud LB — TLS terminates HERE)
                          ├─▶ 127.0.0.1:3000  frontend  (Next.js, static UI)
                          └─▶ 127.0.0.1:8000  api       (FastAPI, REST + WebSocket)
                                   │  network `internal` (internal: true — no outside route)
                                   ├─▶ postgres  (pgvector/pgvector:pg17)   — no published port
                                   └─▶ kafka     (apache/kafka:3.9.0)       — no published port
                               scheduler ──▶ kafka, postgres      (network `internal` + `egress`)
                               api / scheduler ──▶ LLM provider   (network `egress`, outbound HTTPS only)
```

| Service | Build / image | Ports | Depends on | State | Restart | Health check |
|---------|---------------|-------|------------|-------|---------|--------------|
| postgres | `pgvector/pgvector:pg17` | none (internal) | — | volume `postgres_data` | unless-stopped | `pg_isready` |
| kafka | `apache/kafka:3.9.0` | none (internal) | — | volume `kafka_data` | unless-stopped | `kafka-broker-api-versions` |
| migrate | `backend/Dockerfile` | none | postgres healthy | — | no (one-shot) | exit code |
| api | `backend/Dockerfile` | `127.0.0.1:8000` | migrate ok, kafka healthy | volume `model_cache` | unless-stopped | `GET /health/live` |
| scheduler | `backend/Dockerfile` | none | migrate ok, kafka healthy | volume `model_cache` | unless-stopped | none (see limitations) |
| frontend | `frontend/Dockerfile` | `127.0.0.1:3000` | — | none | unless-stopped | `GET /login` |

Public ports: only what the reverse proxy exposes (443). Internal-only: 5432, 9092/9093, 8000, 3000 (loopback).
Service-to-service: api/scheduler → postgres (role `hivemind_app`), api/scheduler → kafka, browser → api (cookie + CORS
allowlist) and browser → api WebSocket (same cookie, Origin allowlist, ownership check).

**Same-site requirement.** The session cookie is `SameSite=Lax; HttpOnly; Secure`. Serve the frontend and the API from
the **same registrable domain** (e.g. `app.example.com` and `api.example.com`) so the browser sends the cookie on the API
and WebSocket requests. Different registrable domains will not work with this authentication design.

## Configuration

All configuration is environment variables (template: `.env.production.example`; real file `.env.production` is
git-ignored). `ENVIRONMENT=production` is forced by the compose file and turns on strict startup validation
(`Settings.assert_production_ready`): the API and the Scheduler **refuse to start** and print every problem when
`JWT_SECRET` is missing/short (<32 chars), `COOKIE_SECURE` is not true, `CORS_ORIGINS` is empty / contains `*` / is not
`https://`, the database URL uses a default password or a superuser role, the LLM provider/key/model is invalid, or a
SASL Kafka setting is incomplete. There is no fallback secret: outside production an empty `JWT_SECRET` becomes a random
per-process value; in production it is an error. Interactive API docs (`/docs`, `/openapi.json`) are disabled in
production.

## First deployment

```bash
cp .env.production.example .env.production        # fill in real values (secret manager / deployment tooling)
docker compose -f docker-compose.prod.yml --env-file .env.production build
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
# create the first administrator (there is no HTTP way to become one) and adopt any pre-auth projects
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm \
  -e HIVEMIND_ADMIN_PASSWORD='<strong password>' api python -m app.cli create-admin --email ops@example.com
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm api \
  python -m app.cli adopt-legacy-projects --email ops@example.com
```

Migrations run **deliberately**: the `migrate` job (`alembic upgrade head`, as the owner role) runs on every
`up`, and never on API start-up. The database role used by the API/Scheduler (`hivemind_app`, created by
`infra/postgres/init-app-role.sh` on first volume initialisation) is not a superuser and has row-level DML only: it
cannot create, alter or drop tables, roles or extensions. Destructive migrations are never applied automatically: review
each new Alembic revision before `up`.

## Security summary

| Control | Status |
|---------|--------|
| Password hashing: Argon2id (`argon2-cffi`); JWT HS256 (PyJWT) with explicit expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`), httpOnly cookie or Bearer header | IMPLEMENTED, TESTED |
| Ownership: projects belong to users; runs/tasks/events/revisions/memories/agent-logs/workflow/telemetry resolve through the project; non-owners get 404 | IMPLEMENTED, TESTED |
| Internal write endpoints (events, tasks, agent-logs, run PATCH, stale runs, metrics) are administrator-only | IMPLEMENTED, TESTED |
| CSRF: cookie-authenticated unsafe requests need an allowlisted `Origin`; CORS is an explicit allowlist with narrow methods/headers | IMPLEMENTED, TESTED |
| WebSocket: Origin allowlist + authentication (cookie / Bearer header, never a URL credential) + run ownership; `last_event_id` replay unchanged | IMPLEMENTED, TESTED |
| Rate limiting (login, register, run creation, memory insertion), configurable, in-memory per process | IMPLEMENTED, TESTED |
| Input limits: body size (413), bounded pagination, field lengths/ranges, UUID/enum validation; 422 responses never echo input | IMPLEMENTED, TESTED |
| Error responses without internals; `X-Request-ID` on every response; secrets redacted in logs | IMPLEMENTED, TESTED |
| Security headers (API: CSP `default-src 'none'`, nosniff, frame deny, no-store, HSTS in production; frontend: CSP, frame deny, Referrer/Permissions-Policy, HSTS) | IMPLEMENTED, TESTED (API) / build-verified (frontend) |
| Containers: non-root, read-only root fs, all capabilities dropped, no-new-privileges, pinned images, `.dockerignore`, constraints-pinned dependencies | IMPLEMENTED, TESTED (static) |
| Liveness (`/health/live`) vs readiness (`/health/ready`: PostgreSQL + Kafka, booleans only) | IMPLEMENTED, TESTED |
| Graceful shutdown: API closes WebSockets → listener → Kafka producer → DB pool; Scheduler handles SIGTERM (finishes the event in flight, `stop_grace_period: 60s`) | IMPLEMENTED (API pool disposal LOCALLY VERIFIED) |

## Known limitations (deployment)

- **TLS termination is external** (reverse proxy / load balancer): not provided here. Without HTTPS the `Secure` cookie is never sent.
- **Kafka is PLAINTEXT on the private compose network.** SASL/TLS is supported by configuration (`KAFKA_SECURITY_PROTOCOL`, `KAFKA_SASL_*`) but requires a broker configured for it: infrastructure outside this repository, NOT VERIFIED.
- **Rate limiting is per API process.** Several replicas each keep their own counters (effective limit = N x configured); strict distributed limits need a shared store. Behind a proxy set `FORWARDED_ALLOW_IPS` to its address, otherwise every client shares the proxy's address.
- **Single host, single instance** of Postgres, Kafka and the Scheduler: no HA/failover, no backups (schedule `pg_dump`/volume snapshots yourself).
- **JWTs are stateless:** logout clears the cookie but a copied token stays valid until it expires (default 60 minutes); there is no server-side revocation. Deactivating a user (`is_active=false`) takes effect immediately.
- **Secrets** come from the environment; integration with an external secret manager is not provided.
- The frontend CSP allows `'unsafe-inline'` scripts/styles (required by Next.js's bootstrap and Tailwind); a nonce-based CSP would need custom middleware.
- The Scheduler has no health check (no HTTP surface); `restart: unless-stopped` covers crashes, not hangs. `GET /api/v1/workflow/stale` (administrators) reports stuck runs.
- Existing projects created before authentication have `owner_id = NULL` and are invisible until an operator runs `adopt-legacy-projects`.
- The WebSocket client reconnects with capped backoff if the session expires (a browser cannot read the handshake status); REST calls redirect to `/login` on 401.
- No live deployment, DNS, certificate or public-internet verification was performed.
