"""
Secret redaction for logs. Exception messages from providers can echo credentials, and tracebacks print them
verbatim, so a logging filter scrubs every record (message AND traceback text) before any handler sees it.

Identifiers (run ids, event ids, UUIDs) are deliberately NOT redacted: they are the correlation keys.
"""

import logging
import traceback

from app.core.config import settings
from app.memory.security import _PATTERNS

REDACTED = "[REDACTED]"
# The "long random token" heuristic would also match UUIDs, i.e. every run/event id: keep those readable.
_PATTERN_LIST = [p for label, p in _PATTERNS if label != "long random token"]


def _configured_secrets() -> list[str]:
    return [s for s in (settings.GROQ_API_KEY, settings.FEATHERLESS_API_KEY) if s and len(s) >= 8]


def redact_secrets(text: str) -> str:
    for secret in _configured_secrets():
        text = text.replace(secret, REDACTED)
    for pattern in _PATTERN_LIST:
        text = pattern.sub(REDACTED, text)
    return text


class SecretRedactingFilter(logging.Filter):
    """Scrub secrets from the formatted message and from the traceback text of every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            cleaned = redact_secrets(message)
            if cleaned != message:
                record.msg, record.args = cleaned, ()
            if record.exc_info and not record.exc_text:
                record.exc_text = "".join(traceback.format_exception(*record.exc_info))
            if record.exc_text:
                record.exc_text = redact_secrets(record.exc_text)
        except Exception:  # logging must never break the caller
            pass
        return True


_FILTER = SecretRedactingFilter()


def install_log_redaction() -> None:
    """Attach the filter to every root handler (idempotent). Call after logging is configured."""
    for handler in logging.getLogger().handlers:
        if _FILTER not in handler.filters:
            handler.addFilter(_FILTER)
