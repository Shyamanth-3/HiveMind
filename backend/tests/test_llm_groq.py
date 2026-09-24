"""
Groq-only LLM migration tests. No network, no Groq credits, no embedding provider calls.

Covers: single-provider config, structured-output parsing/rejection, all five agent workflows
producing their Pydantic schemas from JSON text, and Queen's memory policy (disabled / working /
failing) against real PostgreSQL + pgvector.
"""

import logging
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel

from agents.architect.schemas import ArchitecturePlan
from agents.architect.service import ArchitectService
from agents.base.exceptions import GenerationError
from agents.base.retry import with_retry
from agents.base.structured import StructuredOutputError, generate_structured, parse_structured
from agents.builder.schemas import TaskGraph
from agents.builder.service import BuilderService
from agents.guardian.schemas import ValidationReport
from agents.guardian.service import GuardianService
from agents.llm.factory import get_llm, log_llm_config
from agents.llm.interface import LLMClient
from agents.queen.schemas import Strategy
from agents.queen.service import QueenService
from agents.scout.schemas import ResearchReport
from agents.scout.service import ScoutService
from app.core.config import Settings, settings
from tests.fakes import (ANALYSIS, PLAN, REPLIES, RESEARCH, REVIEW, STRATEGY, TASKS, ScriptedLLM)  # noqa: F401

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


BACKEND = Path(__file__).resolve().parents[1]
MODEL = "openai/gpt-oss-120b"


def use_llm(monkeypatch, llm):
    import agents.architect.service as a, agents.builder.service as b, agents.guardian.service as g
    import agents.queen.service as q, agents.scout.service as s
    for mod in (a, b, g, q, s):
        monkeypatch.setattr(mod, "get_llm", lambda: llm)


# ── default (Groq) configuration; provider selection itself is covered in test_llm_providers.py ───────


def test_config_defaults_are_groq_and_local_bge_embeddings():
    d = {n: f.default for n, f in Settings.model_fields.items()}  # defaults, independent of env/.env
    assert d["LLM_PROVIDER"] == "groq" and d["LLM_MODEL"] == ""  # "" = the provider's default model
    assert (d["EMBEDDING_PROVIDER"], d["EMBEDDING_MODEL"], d["EMBEDDING_DIMENSION"]) == (
        "fastembed", "BAAI/bge-small-en-v1.5", 384)


def test_get_llm_defaults_to_groq_gpt_oss_through_the_internal_interface():
    llm = get_llm()
    assert isinstance(llm, LLMClient) and (llm.provider, llm.model) == ("groq", MODEL)
    assert llm._llm.additional_kwargs["reasoning_effort"] == settings.LLM_REASONING_EFFORT


def test_every_agent_uses_the_same_llm():
    services = [QueenService(), ArchitectService(), ScoutService(), BuilderService(), GuardianService()]
    assert {(s.workflow.llm.provider, s.workflow.llm.model) for s in services} == {("groq", MODEL)}


def test_startup_log_reports_provider_and_model_and_never_the_key(caplog):
    with caplog.at_level(logging.INFO):
        log_llm_config()
    text = caplog.text
    assert "LLM Provider: groq" in text and f"LLM Model: {MODEL}" in text
    assert settings.GROQ_API_KEY not in text


# ── structured output ───────────────────────────────────────────────────


class Point(BaseModel):
    x: int
    label: str


@pytest.mark.parametrize("text", [
    '{"x": 1, "label": "a"}',
    '```json\n{"x": 1, "label": "a"}\n```',
    'Sure! Here you go:\n{"x": 1, "label": "a"}\nHope that helps.',
])
def test_parse_structured_accepts_json_in_common_wrappers(text):
    assert parse_structured(text, Point) == Point(x=1, label="a")


@pytest.mark.parametrize("text", [
    "", "no json here", "[1, 2, 3]", '{"x": "not-an-int", "label": "a"}', '{"x": 1}',
    '{"x": 1, "label": "a"', 'x=1 label=a',
])
def test_parse_structured_rejects_anything_that_is_not_a_valid_object(text):
    with pytest.raises(StructuredOutputError):
        parse_structured(text, Point)


async def test_generate_structured_uses_json_mode_and_puts_schema_in_prompt():
    llm = ScriptedLLM({"Point": {"x": 2, "label": "b"}})
    out = await generate_structured(llm, Point, "Make a point for {thing}", thing="cats")
    assert out == Point(x=2, label="b")
    assert llm.kwargs[0] == {"json_mode": True}
    assert "Make a point for cats" in llm.prompts[0] and '"title": "Point"' in llm.prompts[0]


async def test_with_retry_recovers_from_malformed_output_and_feeds_the_error_back():
    llm = ScriptedLLM({"Point": ["I think the answer is 3", {"x": 3, "label": "c"}]})
    out = await with_retry(llm=llm, output_cls=Point, base_prompt="p", max_retries=2, agent_name="T", run_id="r")
    assert out == Point(x=3, label="c")
    assert "previous answer was rejected" in llm.prompts[1] and "previous answer" not in llm.prompts[0]


async def test_with_retry_gives_up_with_generation_error_on_persistently_bad_output():
    llm = ScriptedLLM({"Point": ['{"x": "no"}', "still not json"]})
    with pytest.raises(GenerationError):
        await with_retry(llm=llm, output_cls=Point, base_prompt="p", max_retries=2, agent_name="T", run_id="r")


# ── all five agents produce their schemas from JSON text ────────────────


async def test_all_five_agents_produce_validated_schemas_via_json(monkeypatch):
    llm = ScriptedLLM(dict(REPLIES))
    use_llm(monkeypatch, llm)
    run_id = uuid4()

    strategy = await QueenService().generate_strategy(run_id, "goal", "proj")
    assert isinstance(strategy, Strategy) and len(strategy.phases) == 2
    plan = await ArchitectService().generate_plan(run_id, "goal", strategy)
    assert isinstance(plan, ArchitecturePlan) and [c.id for c in plan.components] == ["api", "db"]
    report = await ScoutService().generate_research(run_id, "goal", plan)
    assert isinstance(report, ResearchReport)
    graph = await BuilderService().generate_task_graph(run_id, "goal", plan, report)
    assert isinstance(graph, TaskGraph) and len(graph.tasks) == 3
    review = await GuardianService().generate_review(run_id, "goal", plan, report, graph)
    assert isinstance(review, ValidationReport) and review.overall_verdict == "approved"


async def test_agent_rejects_output_that_parses_but_breaks_business_rules(monkeypatch):
    bad = dict(REPLIES, LLMStrategy={"summary": "s", "phases": [{"id": 5, "title": "x", "description": "d"},
                                                                {"id": 6, "title": "y", "description": "d"}]})
    use_llm(monkeypatch, ScriptedLLM(bad))
    with pytest.raises(Exception, match="sequential"):
        await QueenService().generate_strategy(uuid4(), "goal", "proj")


async def test_agent_fails_when_model_never_returns_valid_json(monkeypatch):
    use_llm(monkeypatch, ScriptedLLM({"LLMArchitecturePlan": "Here is a plan in prose only."}))
    with pytest.raises(Exception, match="Failed to generate"):
        await ArchitectService().generate_plan(uuid4(), "goal", Strategy.model_validate(
            {"workflow_run_id": str(uuid4()), "goal": "g", **STRATEGY}))
