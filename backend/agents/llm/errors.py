"""
Provider-neutral LLM errors. Agent and scheduler code only ever sees these, never an SDK exception.

All of them are `GenerationError`s, so the scheduler keeps treating a failed LLM call as an agent failure
(run -> failed, `error_type` = the class name below, never retried by the scheduler; Phase 5 semantics).

Retry ownership (see docs/PROJECT-STATUS.md, Phase 6):
  provider SDK  transport retries (429 with Retry-After, 5xx, connection) inside ONE call   LLM_MAX_RETRIES
  with_retry    only LLMInvalidResponseError (malformed / schema-violating output), with feedback   2 attempts
  scheduler     never re-runs a failed agent; retries only infrastructure (DB / Kafka)
"""

import asyncio

from agents.base.exceptions import GenerationError
from app.core.redaction import redact_secrets


class LLMError(GenerationError):
    """Base class of every error raised by the LLM layer."""


class LLMTimeoutError(LLMError):
    """The provider did not answer within the request timeout."""


class LLMRateLimitError(LLMError):
    """The provider rate-limited the request (after the SDK's own bounded retries)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMAuthenticationError(LLMError):
    """Missing / invalid / unauthorised credentials. Permanent: retrying cannot help."""


class LLMProviderError(LLMError):
    """Any other provider or transport failure (5xx, 4xx, connection)."""


class LLMInvalidResponseError(LLMError):
    """The model answered, but not with usable output (empty, not JSON, wrong schema, bad enum)."""


def _safe(exc: BaseException, limit: int = 400) -> str:
    return redact_secrets(f"{type(exc).__name__}: {exc}")[:limit]


def normalize_llm_error(exc: BaseException, provider: str) -> LLMError:
    """Map any SDK / transport exception onto the neutral hierarchy. Messages are redacted."""
    if isinstance(exc, LLMError):
        return exc
    import httpx
    import openai  # noqa: PLC0415  (both are transport details of the OpenAI-compatible adapters)

    msg = f"[{provider}] {_safe(exc)}"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, openai.APITimeoutError, httpx.TimeoutException)):
        return LLMTimeoutError(msg)
    if isinstance(exc, openai.RateLimitError):
        retry_after = None
        try:
            retry_after = float(exc.response.headers.get("retry-after"))
        except (AttributeError, TypeError, ValueError):
            pass
        return LLMRateLimitError(msg, retry_after)
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMAuthenticationError(msg)
    return LLMProviderError(msg)
