"""
Application configuration via environment variables.

Uses pydantic-settings to load values from .env file.
Every setting here becomes a single source of truth — routers, services,
and middleware all import `settings` instead of reading os.environ directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the HiveMind backend.

    Attributes:
        APP_NAME: Display name used in OpenAPI docs and logging.
        API_V1_PREFIX: URL prefix for all v1 API routes.
        DATABASE_URL: SQLAlchemy connection string for PostgreSQL.
        REDIS_URL: Connection string for Redis pub/sub and caching.
        CORS_ORIGINS: Comma-separated list of allowed frontend origins.
    """

    APP_NAME: str = "HiveMind"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str
    REDIS_URL: str
    CORS_ORIGINS: str = "http://localhost:3000"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC: str = "hivemind.events"
    KAFKA_CONSUMER_GROUP: str = "hivemind-scheduler"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


settings = Settings()