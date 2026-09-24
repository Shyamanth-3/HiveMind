"""
Structured-output helpers shared by all agents. The pipeline itself (schema-in-prompt -> JSON extraction -> Pydantic
validation -> LLMInvalidResponseError) lives in the provider-neutral `agents.llm.interface`; this module keeps the
names agents and tests already use.
"""

from typing import Any, Type, TypeVar

from llama_index.core.prompts import PromptTemplate
from pydantic import BaseModel

from agents.llm.errors import LLMInvalidResponseError
from agents.llm.interface import LLMClient, parse_structured  # noqa: F401  (re-exported)

T = TypeVar("T", bound=BaseModel)

# Kept for compatibility: unusable model output is the neutral LLMInvalidResponseError.
StructuredOutputError = LLMInvalidResponseError


async def generate_structured(
    llm: LLMClient,
    output_cls: Type[T],
    prompt_template: str,
    retry_feedback: str | None = None,
    **prompt_kwargs: Any,
) -> T:
    """One model call -> one validated `output_cls` instance. `retry_feedback` is the previous failure."""
    prompt = PromptTemplate(prompt_template).format(**prompt_kwargs)
    return await llm.structured_output(output_cls, prompt, retry_feedback=retry_feedback)
