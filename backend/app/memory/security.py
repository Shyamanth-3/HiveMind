"""
Deterministic secret detection for memory content. Never rely on prompts alone: everything that
would be stored passes through `find_secret`, and matching content is rejected.
"""

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("API key", re.compile(r"\b(?:gsk|sk|rk|pk)[-_][A-Za-z0-9_\-]{16,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("authorization header", re.compile(r"(?i)\bauthorization\s*[:=]|\bbearer\s+[A-Za-z0-9._\-]{12,}")),
    ("credentials in URL", re.compile(r"[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/@]+@")),
    ("secret assignment", re.compile(
        r"(?i)\b(?:pass(?:word|wd)?|secret|token|api[_\- ]?key|access[_\- ]?key|private[_\- ]?key|credentials?)"
        r"\b\s*(?:is|are|=|:)\s*[\"']?[^\s\"',;]{6,}")),
    ("long random token", re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b")),
]


def find_secret(text: str) -> str | None:
    """Return a label for the first secret-looking pattern in `text`, else None."""
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            return label
    return None
