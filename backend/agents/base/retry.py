"""
Shared retry logic for agent structured generation.
"""

import logging
import time
from typing import TypeVar, Type, Any

from pydantic import BaseModel

from agents.base.exceptions import GenerationError
from agents.base.structured import generate_structured
from agents.llm.errors import LLMInvalidResponseError
from agents.llm.interface import LLMClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

async def with_retry(
    llm: LLMClient,
    output_cls: Type[T],
    base_prompt: str,
    max_retries: int,
    agent_name: str,
    run_id: str,
    **prompt_kwargs: Any,
) -> T:
    """
    Executes a validated structured generation with feedback retries.

    Owns exactly ONE kind of retry: the model answered but the output was unusable (malformed JSON, schema
    violation, bad enum) -> ask again with the failure reason. Provider/transport errors (timeout, rate limit,
    auth, 5xx) are NOT retried here: the provider SDK already retried them inside the call, so retrying again would
    multiply calls (attempts x SDK retries) and re-send requests that can never succeed (auth). They propagate as
    the neutral LLMError subclasses and fail the agent, which is the Phase 5 contract.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        start = time.monotonic()
        feedback = str(last_error)[:600] if last_error else None

        try:
            result = await generate_structured(
                llm, output_cls, base_prompt, retry_feedback=feedback, **prompt_kwargs,
            )

            duration = time.monotonic() - start
            logger.info(
                "[%s] with_retry | run=%s | attempt=%d/%d | duration=%.2fs",
                agent_name, run_id, attempt, max_retries, duration,
            )

            return result

        except LLMInvalidResponseError as e:
            last_error = e
            duration = time.monotonic() - start
            logger.warning(
                "[%s] with_retry | run=%s | attempt=%d/%d | FAILED | error=%s | duration=%.2fs",
                agent_name, run_id, attempt, max_retries, e, duration,
            )

    raise GenerationError(
        f"[{agent_name}] Failed to generate {output_cls.__name__} after {max_retries} attempts: {last_error}"
    )
