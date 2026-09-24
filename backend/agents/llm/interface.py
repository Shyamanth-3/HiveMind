"""
The internal LLM contract: what HiveMind agents need from a language model, and nothing provider-specific.

    complete(prompt, json_mode=False) -> str          one call, plain text
    structured_output(output_cls, prompt, ...) -> T   one call -> one validated Pydantic instance

Providers implement only the transport (`_complete`). Error normalisation, empty-response handling and the whole
structured-output pipeline (schema-in-prompt -> JSON extraction -> Pydantic validation) live here, so every
provider behaves identically and agents keep receiving validated internal models.

Why schema-in-prompt instead of a provider's native structured-output/tool API: it works the same on every
OpenAI-compatible provider, and LlamaIndex's function-calling path fails on gpt-oss (tool_use_failed).
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from agents.llm.errors import LLMError, LLMInvalidResponseError, normalize_llm_error

T = TypeVar("T", bound=BaseModel)

_INSTRUCTIONS = (
    "\n\nRespond with ONLY one JSON object that conforms to this JSON Schema. "
    "No prose, no markdown fences, no comments.\nJSON Schema:\n{schema}\n"
)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_structured(text: str, output_cls: Type[T]) -> T:
    """Extract a JSON object from model text and validate it against `output_cls`."""
    candidate = _FENCE.sub("", (text or "").strip())
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise LLMInvalidResponseError(f"No JSON object in model output: {candidate[:120]!r}")
        candidate = candidate[start:end + 1]
    try:
        return output_cls.model_validate_json(candidate)
    except (ValidationError, ValueError) as e:
        raise LLMInvalidResponseError(f"Output does not match {output_cls.__name__}: {str(e)[:600]}") from e


def build_structured_prompt(output_cls: Type[BaseModel], prompt: str, retry_feedback: str | None = None) -> str:
    prompt += _INSTRUCTIONS.format(schema=json.dumps(output_cls.model_json_schema()))
    if retry_feedback:
        prompt += f"\nYour previous answer was rejected: {retry_feedback}\nReturn a corrected JSON object.\n"
    return prompt


class LLMClient(ABC):
    """Provider-neutral LLM. Agents depend on this class only."""

    provider: str = "unknown"
    model: str = ""

    @abstractmethod
    async def _complete(self, prompt: str, json_mode: bool) -> str:
        """Provider transport: send `prompt`, return the text. May raise anything; `complete` normalises it."""

    async def complete(self, prompt: str, *, json_mode: bool = False) -> str:
        try:
            text = await self._complete(prompt, json_mode)
        except LLMError:
            raise
        except Exception as exc:  # SDK / network / timeout -> neutral error, original kept as __cause__
            raise normalize_llm_error(exc, self.provider) from exc
        return text if isinstance(text, str) else ""

    async def structured_output(
        self, output_cls: Type[T], prompt: str, *, retry_feedback: str | None = None,
    ) -> T:
        """One model call -> one validated `output_cls`. Raises LLMInvalidResponseError on unusable output."""
        text = await self.complete(build_structured_prompt(output_cls, prompt, retry_feedback), json_mode=True)
        return parse_structured(text, output_cls)
