"""
Featherless adapter: Featherless exposes an OpenAI-compatible API, so LlamaIndex's OpenAILike client is used.

JSON mode: `response_format` support differs per hosted model and has not been verified live, so it is NOT sent;
structured output relies on schema-in-prompt + JSON extraction + Pydantic validation (identical to Groq's contract
from the agents' point of view), and unusable output surfaces as LLMInvalidResponseError.
"""

from llama_index.llms.openai_like import OpenAILike

from agents.llm.interface import LLMClient
from app.core.config import settings


class FeatherlessLLM(LLMClient):
    provider = "featherless"

    def __init__(self, model: str | None = None, api_key: str | None = None, api_base: str | None = None):
        self.model = model or settings.LLM_MODEL
        self._llm = OpenAILike(
            model=self.model,
            api_key=api_key or settings.FEATHERLESS_API_KEY,
            api_base=api_base or settings.FEATHERLESS_BASE_URL,
            is_chat_model=True,
            is_function_calling_model=False,
            timeout=settings.LLM_REQUEST_TIMEOUT_S,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    async def _complete(self, prompt: str, json_mode: bool) -> str:
        return (await self._llm.acomplete(prompt)).text
