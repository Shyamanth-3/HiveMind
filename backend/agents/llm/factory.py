"""
The single place that turns configuration into an LLM: settings.LLM_PROVIDER -> adapter.

    configuration -> validate_llm_config() -> get_llm() -> LLMClient -> agents

Agents never import a provider; adding a provider means one adapter + one entry in PROVIDERS.
"""

import logging

from agents.llm.featherless_client import FeatherlessLLM
from agents.llm.groq_client import DEFAULT_MODEL as GROQ_DEFAULT_MODEL, GroqLLM
from agents.llm.interface import LLMClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# provider -> (adapter class, settings attribute holding its credential, default model or None = required)
PROVIDERS: dict[str, tuple[type[LLMClient], str, str | None]] = {
    "groq": (GroqLLM, "GROQ_API_KEY", GROQ_DEFAULT_MODEL),
    "featherless": (FeatherlessLLM, "FEATHERLESS_API_KEY", None),
}


class LLMConfigError(ValueError):
    """The LLM configuration is unusable (unknown provider, missing credential or model)."""


def validate_llm_config(cfg=None) -> tuple[str, str]:
    """Return (provider, model) or raise LLMConfigError with an actionable message. Never includes a secret."""
    cfg = cfg or settings
    provider = (cfg.LLM_PROVIDER or "").strip().lower()
    if provider not in PROVIDERS:
        raise LLMConfigError(f"Unsupported LLM_PROVIDER '{cfg.LLM_PROVIDER}'. Supported: {', '.join(sorted(PROVIDERS))}.")
    _, key_attr, default_model = PROVIDERS[provider]
    if not getattr(cfg, key_attr).strip():
        raise LLMConfigError(f"LLM_PROVIDER={provider} requires {key_attr} to be set.")
    model = cfg.LLM_MODEL.strip() or default_model
    if not model:
        raise LLMConfigError(f"LLM_PROVIDER={provider} requires LLM_MODEL to be set (it has no default model).")
    return provider, model


def get_llm() -> LLMClient:
    """The LLM every agent uses. Same provider and model for all agents (no per-agent routing)."""
    provider, model = validate_llm_config()
    return PROVIDERS[provider][0](model=model)


def log_llm_config() -> None:
    """Validate and log the active LLM configuration (never a credential). Raises LLMConfigError if unusable."""
    provider, model = validate_llm_config()
    logger.info(
        "LLM Provider: %s | LLM Model: %s | timeout=%ss max_retries=%s | agent_timeout=%ss",
        provider, model, settings.LLM_REQUEST_TIMEOUT_S, settings.LLM_MAX_RETRIES, settings.AGENT_TIMEOUT_S,
    )
