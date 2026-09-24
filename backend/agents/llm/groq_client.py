"""Groq adapter: LlamaIndex's Groq client behind the provider-neutral LLMClient contract."""

from llama_index.llms.groq import Groq

from agents.llm.interface import LLMClient
from app.core.config import settings

DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqLLM(LLMClient):
    provider = "groq"

    def __init__(self, model: str | None = None, api_key: str | None = None, api_base: str | None = None):
        self.model = model or settings.LLM_MODEL or DEFAULT_MODEL
        self._llm = Groq(
            model=self.model,
            api_key=api_key or settings.GROQ_API_KEY,
            **({"api_base": api_base} if api_base else {}),  # tests point this at a local fake server
            timeout=settings.LLM_REQUEST_TIMEOUT_S,
            max_retries=settings.LLM_MAX_RETRIES,
            # gpt-oss is a reasoning model: reasoning tokens count against output-token limits
            additional_kwargs={"reasoning_effort": settings.LLM_REASONING_EFFORT},
        )

    async def _complete(self, prompt: str, json_mode: bool) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        return (await self._llm.acomplete(prompt, **kwargs)).text
