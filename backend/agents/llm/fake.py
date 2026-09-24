"""
Deterministic fake provider for tests: no network, no quota. Scripted replies and injectable failures, going through
the SAME LLMClient pipeline as real adapters (error normalisation, empty handling, structured parsing).
"""

import asyncio
from collections import deque

from agents.llm.errors import LLMAuthenticationError, LLMProviderError, LLMRateLimitError, LLMTimeoutError
from agents.llm.interface import LLMClient

_ERRORS = {
    "timeout": lambda: LLMTimeoutError("fake provider timed out"),
    "rate_limit": lambda: LLMRateLimitError("fake provider rate limited", retry_after=1.0),
    "auth": lambda: LLMAuthenticationError("fake provider rejected the credentials"),
    "provider_error": lambda: LLMProviderError("fake provider failed (500)"),
}


class FakeLLM(LLMClient):
    provider = "fake"
    model = "fake-model"

    def __init__(self, replies=None, default: str = "Free-text analysis.", fail: str | None = None):
        """`replies`: list of texts returned in order (the last repeats). `fail`: timeout|rate_limit|auth|provider_error
        (raised on every call) or 'raw_timeout' (a bare asyncio timeout, to prove normalisation)."""
        self._replies = deque(replies or [])
        self._default, self.fail = default, fail
        self.prompts: list[str] = []
        self.json_modes: list[bool] = []

    async def _complete(self, prompt: str, json_mode: bool) -> str:
        self.prompts.append(prompt)
        self.json_modes.append(json_mode)
        if self.fail == "raw_timeout":
            raise asyncio.TimeoutError()
        if self.fail:
            raise _ERRORS[self.fail]()
        if len(self._replies) > 1:
            return self._replies.popleft()
        return self._replies[0] if self._replies else self._default
