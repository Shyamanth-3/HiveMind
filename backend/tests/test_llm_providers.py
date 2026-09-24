"""
Phase 6 — provider-agnostic LLM layer. No live provider is called: adapters are exercised against a local fake
HTTP server (OpenAI-compatible) and the deterministic FakeLLM.
"""

import ast
import copy
import json
import logging
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import BaseModel

import agents.llm.factory as factory
from agents.architect.schemas import ArchitecturePlan
from agents.architect.service import ArchitectService
from agents.base.exceptions import GenerationError
from agents.base.retry import with_retry
from agents.builder.schemas import TaskGraph
from agents.builder.service import BuilderService
from agents.guardian.service import GuardianService
from agents.llm.errors import (
    LLMAuthenticationError, LLMError, LLMInvalidResponseError, LLMProviderError, LLMRateLimitError, LLMTimeoutError,
)
from agents.llm.factory import LLMConfigError, get_llm, log_llm_config, validate_llm_config
from agents.llm.fake import FakeLLM
from agents.llm.featherless_client import FeatherlessLLM
from agents.llm.groq_client import GroqLLM
from agents.llm.interface import LLMClient
from agents.queen.service import QueenService
from agents.scout.schemas import ResearchReport
from agents.scout.service import ScoutService
from app.core.config import settings
from tests.fakes import REPLIES, ScriptedLLM

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Point(BaseModel):
    x: int
    label: str


# ── configuration + factory ─────────────────────────────────────────────


@pytest.fixture
def cfg(monkeypatch):
    def set_(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(settings, k, v)
    return set_


def test_groq_is_selected_with_its_default_model(cfg):
    cfg(LLM_PROVIDER="groq", LLM_MODEL="", GROQ_API_KEY="k" * 20)
    llm = get_llm()
    assert isinstance(llm, GroqLLM) and llm.model == "openai/gpt-oss-120b"


def test_featherless_is_selected_and_requires_an_explicit_model(cfg):
    cfg(LLM_PROVIDER="featherless", LLM_MODEL="acme/some-model", FEATHERLESS_API_KEY="f" * 20)
    llm = get_llm()
    assert isinstance(llm, FeatherlessLLM) and llm.model == "acme/some-model"
    cfg(LLM_MODEL="")
    with pytest.raises(LLMConfigError, match="LLM_MODEL"):
        get_llm()


@pytest.mark.parametrize("provider", ["openai", "", "GROQ2"])
def test_unsupported_provider_is_rejected_with_a_clear_message(cfg, provider):
    cfg(LLM_PROVIDER=provider)
    with pytest.raises(LLMConfigError, match="Unsupported LLM_PROVIDER"):
        validate_llm_config()


@pytest.mark.parametrize("provider,missing", [("groq", "GROQ_API_KEY"), ("featherless", "FEATHERLESS_API_KEY")])
def test_missing_credential_of_the_selected_provider_is_a_startup_error(cfg, provider, missing):
    cfg(LLM_PROVIDER=provider, LLM_MODEL="m", GROQ_API_KEY="", FEATHERLESS_API_KEY="")
    with pytest.raises(LLMConfigError, match=missing):
        log_llm_config()


def test_only_the_selected_providers_credential_is_required(cfg):
    cfg(LLM_PROVIDER="groq", LLM_MODEL="", GROQ_API_KEY="k" * 20, FEATHERLESS_API_KEY="")
    assert validate_llm_config() == ("groq", "openai/gpt-oss-120b")


def test_provider_name_is_case_insensitive(cfg):
    cfg(LLM_PROVIDER=" Groq ", GROQ_API_KEY="k" * 20)
    assert validate_llm_config()[0] == "groq"


def test_startup_log_never_contains_any_credential(cfg, caplog):
    cfg(LLM_PROVIDER="featherless", LLM_MODEL="m/x", FEATHERLESS_API_KEY="fl-secret-" + "z" * 20)
    with caplog.at_level(logging.INFO):
        log_llm_config()
    assert "featherless" in caplog.text and "fl-secret" not in caplog.text


# ── local OpenAI-compatible server for the real adapters ────────────────


class Server:
    mode = "ok"
    content = json.dumps({"x": 1, "label": "a"})
    hits = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        Server.hits += 1
        mode = Server.mode
        if mode == "slow":
            time.sleep(1.5)
        if mode in ("429", "401", "403", "500", "400"):
            self.send_response(int(mode))
            self.send_header("content-type", "application/json")
            if mode == "429":
                self.send_header("retry-after", "7")
            body = json.dumps({"error": {"message": f"boom {mode} key gsk_" + "A1b2C3d4E5f6G7h8I9j0K1l2"}}).encode()
        else:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            body = json.dumps({"id": "c", "object": "chat.completion", "created": 1, "model": "m", "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": Server.content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


@pytest.fixture(params=["groq", "featherless"])
def adapter(request, server, monkeypatch):
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(settings, "LLM_REQUEST_TIMEOUT_S", 0.5)
    Server.mode, Server.content, Server.hits = "ok", json.dumps({"x": 1, "label": "a"}), 0
    if request.param == "groq":
        return GroqLLM(model="m", api_key="k" * 20, api_base=server)
    return FeatherlessLLM(model="m", api_key="k" * 20, api_base=server)


async def test_both_adapters_complete_and_produce_structured_output(adapter):
    assert isinstance(adapter, LLMClient)
    assert await adapter.complete("hi") == Server.content
    assert await adapter.structured_output(Point, "make a point") == Point(x=1, label="a")


@pytest.mark.parametrize("mode,exc", [
    ("429", LLMRateLimitError), ("401", LLMAuthenticationError), ("403", LLMAuthenticationError),
    ("500", LLMProviderError), ("400", LLMProviderError), ("slow", LLMTimeoutError),
])
async def test_provider_errors_are_normalised_identically_for_every_adapter(adapter, mode, exc):
    Server.mode = mode
    with pytest.raises(exc) as e:
        await adapter.complete("hi")
    assert isinstance(e.value, LLMError) and isinstance(e.value, GenerationError)
    assert "gsk_A1b2C3d4" not in str(e.value)  # provider error text is redacted
    if mode == "429":
        assert e.value.retry_after == 7.0


async def test_sdk_retries_are_bounded_by_llm_max_retries(adapter):
    Server.mode = "500"
    with pytest.raises(LLMProviderError):
        await adapter.complete("hi")
    assert Server.hits == 1  # LLM_MAX_RETRIES=0: no hidden retry


@pytest.mark.parametrize("content", ["", "no json here", '{"x": "not-int", "label": "a"}', '{"x": 1}', "[1, 2]"])
async def test_malformed_missing_or_wrong_typed_output_is_an_invalid_response(adapter, content):
    Server.content = content
    with pytest.raises(LLMInvalidResponseError):
        await adapter.structured_output(Point, "p")


# ── retry ownership ─────────────────────────────────────────────────────


async def test_with_retry_retries_only_invalid_output_with_feedback():
    llm = FakeLLM(replies=["oops", '{"x": 3, "label": "c"}'])
    got = await with_retry(llm, Point, "make a point", 2, "T", "run")
    assert got == Point(x=3, label="c") and len(llm.prompts) == 2 and "rejected" in llm.prompts[1]


@pytest.mark.parametrize("fail,exc", [("timeout", LLMTimeoutError), ("rate_limit", LLMRateLimitError),
                                     ("auth", LLMAuthenticationError), ("provider_error", LLMProviderError),
                                     ("raw_timeout", LLMTimeoutError)])
async def test_transport_errors_are_not_retried_by_the_agent_layer(fail, exc):
    llm = FakeLLM(fail=fail)
    with pytest.raises(exc):
        await with_retry(llm, Point, "p", 5, "T", "run")
    assert len(llm.prompts) == 1  # one call, not 5: no retry multiplication


async def test_persistently_invalid_output_ends_as_a_generation_error():
    llm = FakeLLM(replies=["nope"])
    with pytest.raises(GenerationError, match="after 2 attempts"):
        await with_retry(llm, Point, "p", 2, "T", "run")
    assert len(llm.prompts) == 2


async def test_fake_provider_scripts_and_records_calls():
    llm = FakeLLM(replies=['{"x": 1, "label": "a"}'])
    assert (await llm.structured_output(Point, "p")).x == 1
    assert llm.json_modes == [True] and await llm.complete("q") and llm.json_modes == [True, False]


# ── agents use the interface; provider switching is configuration only ──────────────────────────────────

AGENTS = [QueenService, ArchitectService, ScoutService, BuilderService, GuardianService]


@pytest.mark.parametrize("provider", ["groq", "featherless"])
def test_every_agent_receives_the_configured_provider_without_agent_changes(cfg, provider):
    cfg(LLM_PROVIDER=provider, LLM_MODEL="acme/m", GROQ_API_KEY="k" * 20, FEATHERLESS_API_KEY="f" * 20)
    expected = {"groq": GroqLLM, "featherless": FeatherlessLLM}[provider]
    for svc_cls in AGENTS:
        assert isinstance(svc_cls().workflow.llm, expected)


async def _run_all_agents(goal="Build a thing"):
    rid = uuid.uuid4()
    strategy = await QueenService().generate_strategy(rid, goal, "proj")
    plan = await ArchitectService().generate_plan(rid, goal, strategy)
    research = await ScoutService().generate_research(rid, goal, plan)
    graph = await BuilderService().generate_task_graph(rid, goal, plan, research)
    report = await GuardianService().generate_review(rid, goal, plan, research, graph)
    return plan, graph, report


async def test_all_five_agents_run_through_the_factory_on_a_swapped_provider(monkeypatch, cfg):
    """Same agents, same workflows, same interface; the implementation behind LLM_PROVIDER is swapped."""
    llm = ScriptedLLM(dict(REPLIES))
    monkeypatch.setitem(factory.PROVIDERS, "fake", (lambda model=None: llm, "GROQ_API_KEY", "fake-model"))
    cfg(LLM_PROVIDER="fake", GROQ_API_KEY="k" * 20)
    plan, graph, report = await _run_all_agents()
    assert isinstance(plan, ArchitecturePlan) and graph.tasks and report.overall_verdict == "approved"
    assert len(llm.prompts) >= 9  # every agent really went through the injected implementation


@pytest.mark.parametrize("provider", ["groq", "featherless"])
async def test_agents_produce_the_same_result_through_each_real_adapter(provider, server, monkeypatch, cfg):
    """The real adapter objects (transport stubbed with scripted text) drive all five agents to identical validated outputs."""
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 0)
    cfg(LLM_PROVIDER=provider, LLM_MODEL="m", GROQ_API_KEY="k" * 20, FEATHERLESS_API_KEY="f" * 20)
    scripted = ScriptedLLM(dict(REPLIES))
    real = get_llm()
    Server.mode = "ok"

    async def via_server(prompt, json_mode):  # the adapter's transport is replaced by the scripted text
        return await scripted._complete(prompt, json_mode)

    monkeypatch.setattr(real, "_complete", via_server)
    monkeypatch.setattr(factory, "get_llm", lambda: real)
    import agents.architect.service as a, agents.builder.service as b, agents.guardian.service as g
    import agents.queen.service as q, agents.scout.service as s
    for mod in (a, b, g, q, s):
        monkeypatch.setattr(mod, "get_llm", lambda: real)
    plan, graph, report = await _run_all_agents()
    assert real.provider == provider and report.overall_verdict == "approved" and len(graph.tasks) == 3


@pytest.mark.parametrize("verdict", ["maybe", "", "APPROVED", "pass"])
async def test_invalid_guardian_verdict_never_reaches_the_workflow(monkeypatch, verdict):
    import agents.guardian.service as gs
    replies = copy.deepcopy(REPLIES)
    replies["LLMValidationReport"] = {**replies["LLMValidationReport"], "overall_verdict": verdict}
    monkeypatch.setattr(gs, "get_llm", lambda: ScriptedLLM(replies))
    from tests import fakes
    rid = uuid.uuid4()
    with pytest.raises(GenerationError):
        await GuardianService().generate_review(
            rid, "g", ArchitecturePlan(workflow_run_id=rid, goal="g", **fakes.PLAN),
            ResearchReport(workflow_run_id=rid, goal="g", **fakes.RESEARCH),
            TaskGraph(workflow_run_id=rid, goal="g", summary="s", tasks=[]))


@pytest.mark.parametrize("fail,exc", [("timeout", LLMTimeoutError), ("rate_limit", LLMRateLimitError),
                                     ("auth", LLMAuthenticationError), ("provider_error", LLMProviderError)])
async def test_agent_workflows_surface_neutral_llm_errors(monkeypatch, fail, exc):
    import agents.queen.service as qs
    monkeypatch.setattr(qs, "get_llm", lambda: FakeLLM(fail=fail))
    with pytest.raises(exc):
        await QueenService().generate_strategy(uuid.uuid4(), "Build a thing", "proj")


# ── architectural enforcement: agents/app never touch a concrete provider ───────────────────────────────

_FORBIDDEN_MODULES = ("llama_index.llms", "llama_index.core.llms", "openai", "groq", "httpx",
                      "agents.llm.groq_client", "agents.llm.featherless_client")
_PROVIDER_SETTINGS = re.compile(r"\b(GROQ_API_KEY|FEATHERLESS_API_KEY|FEATHERLESS_BASE_URL)\b")
# Allowed: the adapters/factory/error mapping, and config/redaction which must know the secret names.
_ALLOWED = {"agents/llm/groq_client.py", "agents/llm/featherless_client.py", "agents/llm/factory.py",
            "agents/llm/errors.py", "app/core/config.py", "app/core/redaction.py"}


def _python_files():
    for d in ("agents", "app"):
        for p in (BACKEND / d).rglob("*.py"):
            rel = p.relative_to(BACKEND).as_posix()
            if "__pycache__" not in rel and rel not in _ALLOWED and "agent_old" not in rel:
                yield rel, p


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_no_agent_or_app_module_imports_a_concrete_provider_or_sdk():
    offenders = []
    for rel, p in _python_files():
        for mod in _imports(ast.parse(p.read_text(encoding="utf-8"))):
            if any(mod == f or mod.startswith(f + ".") for f in _FORBIDDEN_MODULES):
                offenders.append(f"{rel}: import {mod}")
    assert offenders == []


def test_provider_credentials_are_only_referenced_by_config_factory_adapters_and_redaction():
    offenders = [rel for rel, p in _python_files() if _PROVIDER_SETTINGS.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_agent_code_does_not_name_a_provider_at_all():
    offenders = [rel for rel, p in _python_files()
                 if rel.startswith("agents/") and not rel.startswith("agents/llm/")
                 and re.search(r"\b(groq|featherless)\b", p.read_text(encoding="utf-8"), re.IGNORECASE)]
    assert offenders == []


def test_env_example_holds_placeholders_only_and_env_is_ignored():
    example = (BACKEND.parent / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"gsk_[A-Za-z0-9]{10,}|sk-[A-Za-z0-9]{10,}", example)
    assert "your_groq_api_key_here" in example and "your_featherless_api_key_here" in example
    gi = (BACKEND.parent / ".gitignore").read_text(encoding="utf-8") + (BACKEND / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", gi, re.MULTILINE)
