import secrets
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """The configuration is unusable for the selected ENVIRONMENT. Lists every problem; never a secret value."""


class Settings(BaseSettings):

    # development | test | production. ONE switch: production turns on strict startup validation
    # (assert_production_ready) and disables the interactive API docs; nothing else branches on it.
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "HiveMind"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"  # unused by the pipeline (Kafka is the bus)
    # Explicit browser origins allowed to call the API and open WebSockets (comma separated, never "*").
    CORS_ORIGINS: str = "http://localhost:3000"

    # ==========================
    # Authentication (JWT in an httpOnly cookie, or an Authorization: Bearer header for non-browser clients)
    # ==========================
    # REQUIRED (>= 32 chars) in production. Outside production an empty value becomes a random per-process secret
    # (sessions do not survive a restart); there is deliberately NO hard-coded fallback secret.
    JWT_SECRET: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    SESSION_COOKIE_NAME: str = "hm_session"
    COOKIE_SECURE: bool = False  # must be True in production (HTTPS only)
    REGISTRATION_ENABLED: bool = True

    # ==========================
    # Abuse protection (in-memory, per API process: see docs for the horizontal-scaling limitation)
    # ==========================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_PER_MIN: int = 10        # per client IP
    RATE_LIMIT_REGISTER_PER_HOUR: int = 10    # per client IP
    RATE_LIMIT_RUNS_PER_HOUR: int = 30        # per user: every run triggers paid LLM calls
    RATE_LIMIT_MEMORY_PER_MIN: int = 30       # per user
    MAX_REQUEST_BYTES: int = 1_000_000
    API_DEFAULT_LIMIT: int = 100
    API_MAX_LIMIT: int = 500

    # Database pool (API process)
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_S: int = 1800

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC: str = "hivemind.events"
    KAFKA_CONSUMER_GROUP: str = "hivemind-scheduler"
    # Optional client security for a secured broker (e.g. SASL_SSL). Empty = the client default (PLAINTEXT):
    # only acceptable on a private network. Applied to BOTH the producer and the consumer.
    KAFKA_SECURITY_PROTOCOL: str = ""
    KAFKA_SASL_MECHANISM: str = ""
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""

    # ==========================
    # LLM: provider-agnostic. LLM_PROVIDER selects the adapter (groq | featherless); credentials are per provider
    # and validated by agents.llm.factory (a missing key is a clear startup error, not a runtime surprise).
    # ==========================

    LLM_PROVIDER: str = "groq"
    # "" = the provider's default (groq: openai/gpt-oss-120b). Featherless has no default: set LLM_MODEL.
    LLM_MODEL: str = ""
    GROQ_API_KEY: str = ""
    FEATHERLESS_API_KEY: str = ""
    FEATHERLESS_BASE_URL: str = "https://api.featherless.ai/v1"
    # One HTTP request; and the SDK's own bounded transport retries (429 Retry-After / 5xx / connection)
    LLM_REQUEST_TIMEOUT_S: float = 120.0
    LLM_MAX_RETRIES: int = 3
    # low|medium|high. Structured planning needs little reasoning; "low" keeps output tokens down.
    LLM_REASONING_EFFORT: str = "low"
    # LlamaIndex Workflows default to 45s, too short for a reasoning model
    AGENT_TIMEOUT_S: float = 300.0
    # Guardian revision loop: max Builder revisions per run (0 = a needs_revision verdict fails the run)
    MAX_REVISIONS: int = 3
    # A run still "running" with no event for this long is REPORTED as stale (never auto-failed: see docs)
    STALE_RUN_MINUTES: int = 30

    # ==========================
    # Embeddings + semantic memory (PostgreSQL + pgvector)
    # ==========================
    # Local ONNX model via fastembed: no API key, deterministic. "none" disables memory.
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    # Must equal the model's output size AND the agent_memories.embedding column (checked at startup)
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_CACHE_DIR: str = ".model_cache"
    # A hung embedding call must fail fast (the worker thread cannot be killed, but the run must not wait on it)
    EMBEDDING_TIMEOUT_S: float = 30.0
    MEMORY_TOP_K: int = 5
    # cosine; bge-small measured: relevant 0.65-0.82, unrelated 0.45-0.58 (see docs/PROJECT-STATUS.md)
    MEMORY_MIN_SIMILARITY: float = 0.60
    # a new memory this similar to an existing one (same project + type) is a duplicate
    MEMORY_DEDUP_SIMILARITY: float = 0.95
    MEMORY_MAX_PER_RUN: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _ephemeral_dev_secret(self) -> "Settings":
        if not self.JWT_SECRET and self.ENVIRONMENT != "production":
            self.JWT_SECRET = secrets.token_urlsafe(48)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def production_problems(self) -> list[str]:
        """Everything that makes this configuration unsafe for production (no secret values in the messages)."""
        from sqlalchemy.engine import make_url

        problems: list[str] = []
        if len(self.JWT_SECRET) < 32:
            problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if not self.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true (the session cookie must be HTTPS-only)")
        origins = self.cors_origin_list
        if not origins:
            problems.append("CORS_ORIGINS must list the trusted frontend origin(s)")
        for o in origins:
            if o == "*" or "*" in o:
                problems.append("CORS_ORIGINS must not contain a wildcard")
            elif not o.startswith("https://"):
                problems.append(f"CORS_ORIGINS entry {o!r} must use https://")
        try:
            url = make_url(self.DATABASE_URL)
            if not url.password or url.password in {"password", "postgres", "hivemind", "admin", "changeme"}:
                problems.append("DATABASE_URL must use a real (non-default) password")
            if url.username in {"postgres", "root"}:
                problems.append("DATABASE_URL must use a dedicated non-superuser application role")
        except Exception:
            problems.append("DATABASE_URL is not a valid database URL")
        if self.ACCESS_TOKEN_EXPIRE_MINUTES < 1 or self.ACCESS_TOKEN_EXPIRE_MINUTES > 24 * 60:
            problems.append("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440")
        if self.KAFKA_SECURITY_PROTOCOL.upper().startswith("SASL") and not (
                self.KAFKA_SASL_MECHANISM and self.KAFKA_SASL_USERNAME and self.KAFKA_SASL_PASSWORD):
            problems.append("KAFKA_SASL_MECHANISM/USERNAME/PASSWORD are required with a SASL security protocol")
        try:
            from agents.llm.factory import validate_llm_config
            validate_llm_config(self)
        except Exception as e:  # LLMConfigError: actionable, secret-free
            problems.append(str(e))
        return problems

    def assert_production_ready(self) -> None:
        """Fail startup, listing every problem, when ENVIRONMENT=production and the configuration is unsafe."""
        if not self.is_production:
            return
        problems = self.production_problems()
        if problems:
            raise ConfigurationError("Unsafe production configuration:\n - " + "\n - ".join(problems))


settings = Settings()