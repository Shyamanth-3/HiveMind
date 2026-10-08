"""Kafka client security settings shared by the API producer and the Scheduler consumer."""

from app.core.config import settings


def kafka_security_config() -> dict[str, str]:
    """librdkafka security options from settings. Empty settings add nothing (PLAINTEXT: private networks only)."""
    conf: dict[str, str] = {}
    if settings.KAFKA_SECURITY_PROTOCOL:
        conf["security.protocol"] = settings.KAFKA_SECURITY_PROTOCOL
    if settings.KAFKA_SASL_MECHANISM:
        conf["sasl.mechanism"] = settings.KAFKA_SASL_MECHANISM
        conf["sasl.username"] = settings.KAFKA_SASL_USERNAME
        conf["sasl.password"] = settings.KAFKA_SASL_PASSWORD
    return conf
