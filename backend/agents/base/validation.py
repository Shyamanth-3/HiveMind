"""
Shared validation helpers for agent outputs.
"""
from typing import Any, Sequence


def validate_non_empty(value: str | None, field_name: str) -> str | None:
    """Returns an error message if the value is empty, otherwise None."""
    if not value or not value.strip():
        return f"{field_name} is empty."
    return None


def validate_min_max_count(items: Sequence[Any], min_count: int, max_count: int, label: str) -> str | None:
    """Returns an error message if the item count is out of bounds, otherwise None."""
    if len(items) < min_count:
        return f"Expected at least {min_count} {label}, got {len(items)}."
    if len(items) > max_count:
        return f"Expected at most {max_count} {label}, got {len(items)}."
    return None


def validate_sequential_ids(items: Sequence[Any], id_attr: str = "id") -> str | None:
    """
    Returns an error message if the items don't have sequential IDs starting from 1.
    Assumes items have an attribute named `id_attr`.
    """
    expected_ids = list(range(1, len(items) + 1))
    actual_ids = [getattr(item, id_attr) for item in items]
    if actual_ids != expected_ids:
        return f"IDs must be sequential {expected_ids}, got {actual_ids}."
    return None
