"""
Memory extraction: what deserves to be remembered.

The LLM only *proposes* candidates (strict schema). What actually gets stored is decided here,
deterministically: allowed type, sane length, no secrets, no duplicates, capped per run.
Whole agent outputs, prompts and transient run data are never stored.
"""

import logging
from collections import Counter

from pydantic import BaseModel, Field

from app.memory.schemas import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, MemoryType
from app.memory.security import find_secret

logger = logging.getLogger(__name__)


class MemoryCandidate(BaseModel):
    """One proposed memory. Fields are lenient on purpose: bad items are dropped individually."""
    memory_type: str = Field(description="One of: fact, decision, preference, context, lesson")
    content: str = Field(description="A standalone statement that will still be useful in a future run.")
    importance: int = Field(default=3, description="1 (minor) to 5 (critical)")


class MemoryExtraction(BaseModel):
    """Structured LLM output for memory extraction."""
    memories: list[MemoryCandidate] = Field(default_factory=list)


def sanitize_candidates(extraction: MemoryExtraction, max_items: int) -> list[tuple[MemoryType, str, int]]:
    """Return at most `max_items` valid (type, content, importance), best importance first."""
    kept: list[tuple[MemoryType, str, int]] = []
    dropped: Counter[str] = Counter()
    seen: set[str] = set()

    for cand in extraction.memories:
        try:
            mtype = MemoryType(cand.memory_type.strip().lower())
        except ValueError:
            dropped["bad type"] += 1
            continue
        content = " ".join(cand.content.split())
        if not (MIN_CONTENT_CHARS <= len(content) <= MAX_CONTENT_CHARS):
            dropped["bad length"] += 1
            continue
        if not (1 <= cand.importance <= 5):
            dropped["bad importance"] += 1
            continue
        if find_secret(content):
            dropped["secret"] += 1
            continue
        key = f"{mtype.value}:{content.lower()}"
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        kept.append((mtype, content, cand.importance))

    kept.sort(key=lambda t: -t[2])  # stable: ties keep the model's order
    if len(kept) > max_items:
        dropped["over cap"] += len(kept) - max_items
        kept = kept[:max_items]
    if dropped:
        logger.info("Memory extraction: kept %d, dropped %s", len(kept), dict(dropped))
    return kept
