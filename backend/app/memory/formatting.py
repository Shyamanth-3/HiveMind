"""Deterministic formatting of retrieved memories for an agent prompt."""

from app.memory.schemas import MemorySearchResult

NO_MEMORIES = "Relevant HiveMind Memory:\nNo relevant memories found."


def format_memory_context(memories: list[MemorySearchResult]) -> str:
    """
    'Relevant HiveMind Memory:' + numbered '[type] content' lines, best match first.
    No vectors, ids or scores are exposed to the LLM.
    """
    if not memories:
        return NO_MEMORIES
    lines = [f"{i}. [{m.memory_type.value}] {m.content}" for i, m in enumerate(memories, 1)]
    return "Relevant HiveMind Memory:\n" + "\n".join(lines)
