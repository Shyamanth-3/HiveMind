# syntax=docker/dockerfile:1
# HiveMind backend image: used by the API, the Scheduler and the one-shot migration job (different commands).
# Deterministic: dependencies are installed against constraints.txt (exact versions). No secrets are copied or
# baked in: configuration arrives through the environment at run time.

FROM python:3.13-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    EMBEDDING_CACHE_DIR=/models
# Unprivileged user; /models is the only writable location (local embedding model cache, mounted as a volume).
RUN groupadd --system --gid 10001 hivemind \
 && useradd --system --uid 10001 --gid hivemind --home-dir /app --shell /usr/sbin/nologin hivemind \
 && mkdir /models && chown hivemind:hivemind /models
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY agents ./agents
USER 10001:10001
EXPOSE 8000
# Health checks are defined per service in docker-compose.prod.yml (the Scheduler shares this image).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
