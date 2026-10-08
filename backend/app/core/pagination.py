"""Bounded pagination for list endpoints (responses stay plain arrays: no client change)."""

from dataclasses import dataclass

from fastapi import Query

from app.core.config import settings


@dataclass
class Page:
    limit: int
    offset: int


def page_params(
    limit: int = Query(settings.API_DEFAULT_LIMIT, ge=1, le=settings.API_MAX_LIMIT, description="Max items"),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> Page:
    return Page(limit, offset)
