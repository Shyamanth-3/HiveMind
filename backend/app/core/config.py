from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    APP_NAME: str = "HiveMind"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"  # unused by the pipeline (Kafka is the bus)
    CORS_ORIGINS: str = "http://localhost:3000"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC: str = "hivemind.events"
    KAFKA_CONSUMER_GROUP: str = "hivemind-scheduler"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
        ]


settings = Settings()