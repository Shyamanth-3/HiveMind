"""
Phase 7 — security: authentication, authorization/ownership, CSRF/CORS/Origin, WebSocket authentication, rate
limiting, input validation, error/secret hygiene, headers, health/readiness. Real registration, real cookies and
tokens (`real_auth` opts out of the default test user). Deterministic: fake bus, fake agents, no LLM.
"""

import logging
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.dependencies import get_event_bus
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.events.schemas import KafkaEvent
from app.main import app
from app.models import AgentLog, Project, Task, User
from app.scheduler.consumer import SchedulerConsumer
from tests import fakes

pytestmark = pytest.mark.real_auth

ORIGIN = "http://localhost:3000"
H = {"Origin": ORIGIN}
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _clean(session_factory, monkeypatch):
    limiter.reset()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)  # enabled explicitly by the rate-limit tests
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def make_client(session_factory, bus):
    def override_get_db():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_bus] = lambda: bus

    def factory() -> TestClient:
        return TestClient(app)  # own cookie jar per client; no lifespan (no Kafka)
    return factory


def register(c: TestClient, email="a@example.com", password=PASSWORD):
    return c.post("/api/v1/auth/register", json={"email": email, "password": password})


@pytest.fixture
def alice(make_client):
    c = make_client()
    assert register(c, "alice@example.com").status_code == 201
    return c


@pytest.fixture
def bob(make_client):
    c = make_client()
    assert register(c, "bob@example.com").status_code == 201
    return c


def new_run(c: TestClient, goal="Build a thing"):
    pid = c.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}, headers=H).json()["id"]
    run = c.post("/api/v1/runs/", json={"project_id": pid, "goal": goal}, headers=H)
    assert run.status_code == 201
    return pid, run.json()["id"]


def make_admin(session_factory, email):
    with session_factory() as s:
        s.execute(text("UPDATE users SET is_admin = true WHERE email = :e"), {"e": email})
        s.commit()


# ══ authentication ═══════════════════════════════════════════════════════


def test_register_sets_an_httponly_session_cookie_and_never_returns_secrets(make_client, session_factory):
    c = make_client()
    r = register(c)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "email", "is_admin"} and r.json()["is_admin"] is False
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert PASSWORD not in r.text and "hash" not in r.text.lower()
    with session_factory() as s:
        stored = s.scalar(select(User.password_hash))
    assert stored.startswith("$argon2id$") and PASSWORD not in stored  # strong hash, never plaintext


def test_email_is_case_insensitive_and_duplicates_are_rejected(make_client):
    c = make_client()
    assert register(c, "Mixed@Example.com").status_code == 201
    assert register(make_client(), "mixed@example.com").status_code == 409


@pytest.mark.parametrize("pw", ["short", "x" * 129, ""])
def test_weak_or_oversized_passwords_are_rejected_without_echoing_them(make_client, pw):
    r = register(make_client(), password=pw)
    assert r.status_code == 422 and (pw == "" or pw not in r.text) and "input" not in r.text


def test_registration_can_be_disabled(make_client, monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", False)
    assert register(make_client()).status_code == 403


def test_login_success_wrong_password_and_unknown_email_are_indistinguishable(make_client, alice):
    ok = make_client().post("/api/v1/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and "hm_session" in ok.headers["set-cookie"]
    bad = make_client().post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password-1"})
    unknown = make_client().post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert (bad.status_code, bad.json()) == (unknown.status_code, unknown.json()) == (401, {"detail": "Invalid email or password"})


@pytest.mark.parametrize("payload", [{}, {"email": "not-an-email", "password": "x"}, {"email": "a@b.co"},
                                    {"email": "a@b.co", "password": ["list"]}])
def test_malformed_login_payloads_are_422(make_client, payload):
    assert make_client().post("/api/v1/auth/login", json=payload).status_code == 422


def test_me_requires_authentication_and_accepts_cookie_or_bearer(make_client, alice):
    assert make_client().get("/api/v1/auth/me").status_code == 401
    assert alice.get("/api/v1/auth/me").json()["email"] == "alice@example.com"
    token = alice.cookies.get("hm_session")
    assert make_client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def _token(sub, **over):
    now = int(time.time())
    claims = {"sub": sub, "iat": now, "exp": now + 600, "typ": "access", **over}
    return jwt.encode(claims, over.pop("_secret", settings.JWT_SECRET) if False else settings.JWT_SECRET, "HS256")


@pytest.mark.parametrize("bad", ["expired", "wrong_secret", "wrong_type", "no_exp", "garbage", "alg_none", "unknown_user"])
def test_invalid_tokens_are_rejected_generically(make_client, alice, bad):
    uid = alice.get("/api/v1/auth/me").json()["id"]
    now = int(time.time())
    tokens = {
        "expired": jwt.encode({"sub": uid, "iat": now - 100, "exp": now - 10, "typ": "access"}, settings.JWT_SECRET, "HS256"),
        "wrong_secret": jwt.encode({"sub": uid, "iat": now, "exp": now + 99, "typ": "access"}, "x" * 40, "HS256"),
        "wrong_type": _token(uid, typ="refresh"),
        "no_exp": jwt.encode({"sub": uid, "iat": now}, settings.JWT_SECRET, "HS256"),
        "garbage": "not.a.jwt",
        "alg_none": jwt.encode({"sub": uid, "iat": now, "exp": now + 99, "typ": "access"}, None, algorithm="none"),
        "unknown_user": _token("00000000-0000-4000-8000-00000000dead"),
    }
    r = make_client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens[bad]}"})
    assert r.status_code == 401 and r.json() == {"detail": "Not authenticated"}
    assert tokens[bad] not in r.text


def test_deactivated_users_lose_access_immediately(alice, session_factory):
    with session_factory() as s:
        s.execute(text("UPDATE users SET is_active = false"))
        s.commit()
    assert alice.get("/api/v1/auth/me").status_code == 401


def test_logout_clears_the_cookie(alice):
    r = alice.post("/api/v1/auth/logout", headers=H)
    assert r.status_code == 204 and "hm_session" in r.headers["set-cookie"]
    assert alice.get("/api/v1/auth/me").status_code == 401


# ══ every protected endpoint needs authentication ════════════════════════

PROTECTED = [
    ("get", "/api/v1/projects/"), ("post", "/api/v1/projects/"), ("get", "/api/v1/projects/x"),
    ("patch", "/api/v1/projects/x"), ("delete", "/api/v1/projects/x"),
    ("get", "/api/v1/runs/"), ("post", "/api/v1/runs/"), ("get", "/api/v1/runs/x"), ("patch", "/api/v1/runs/x"),
    ("get", "/api/v1/tasks/"), ("post", "/api/v1/tasks/"), ("get", "/api/v1/tasks/x"), ("patch", "/api/v1/tasks/x"),
    ("get", "/api/v1/events/?run_id=x"), ("get", "/api/v1/events/recent"), ("post", "/api/v1/events/"),
    ("get", "/api/v1/memory/"), ("post", "/api/v1/memory/"),
    ("get", "/api/v1/agent-logs/?run_id=x"), ("get", "/api/v1/agent-logs/cost-summary"), ("post", "/api/v1/agent-logs/"),
    ("get", "/api/v1/system/agents"), ("get", "/api/v1/system/services"),
    ("get", "/api/v1/workflow/stale"), ("get", "/api/v1/workflow/x/status"), ("get", "/api/v1/workflow/x/outputs"),
    ("get", "/health/metrics"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_protected_endpoint_rejects_anonymous_callers(make_client, method, path):
    r = getattr(make_client(), method)(path, **({"json": {}} if method in ("post", "patch") else {}))
    assert r.status_code == 401, (method, path, r.status_code)


def test_public_endpoints_are_only_the_documented_ones(make_client):
    c = make_client()
    assert c.get("/health/").status_code == 200 and c.get("/health/live").json() == {"status": "alive"}
    assert "websocket_runs" not in c.get("/health/").json()  # run ids are never public


# ══ authorization / ownership ════════════════════════════════════════════


def test_users_only_see_their_own_projects_runs_tasks_events(alice, bob):
    pid_a, run_a = new_run(alice)
    pid_b, run_b = new_run(bob)
    assert [p["id"] for p in alice.get("/api/v1/projects/").json()] == [pid_a]
    assert [p["id"] for p in bob.get("/api/v1/projects/").json()] == [pid_b]
    assert [r["id"] for r in bob.get("/api/v1/runs/").json()] == [run_b]
    assert bob.get("/api/v1/tasks/").json() == [] and bob.get("/api/v1/events/recent").json() == []


@pytest.mark.parametrize("path", ["/api/v1/projects/{p}", "/api/v1/runs/{r}", "/api/v1/events/?run_id={r}",
                                  "/api/v1/agent-logs/?run_id={r}", "/api/v1/tasks/?run_id={r}",
                                  "/api/v1/workflow/{r}/status", "/api/v1/workflow/{r}/outputs",
                                  "/api/v1/memory/?project_id={p}", "/api/v1/runs/?project_id={p}"])
def test_guessing_another_users_uuid_never_works(alice, bob, path):
    pid, rid = new_run(alice)
    url = path.format(p=pid, r=rid)
    mine, theirs = alice.get(url), bob.get(url)
    assert mine.status_code == 200 or path.endswith("{p}") and mine.status_code == 200
    if "?project_id" in path and "/runs/" in path:
        assert theirs.status_code == 200 and theirs.json() == []  # filter cannot widen the caller's scope
    else:
        assert theirs.status_code == 404 and theirs.json() == {"detail": "Not found"}


def test_other_users_cannot_modify_or_delete_or_run_in_my_project(alice, bob):
    pid, rid = new_run(alice)
    assert bob.patch(f"/api/v1/projects/{pid}", json={"name": "hacked"}, headers=H).status_code == 404
    assert bob.delete(f"/api/v1/projects/{pid}", headers=H).status_code == 404
    assert bob.post("/api/v1/runs/", json={"project_id": pid, "goal": "steal"}, headers=H).status_code == 404
    assert bob.post("/api/v1/memory/", json={"project_id": pid, "content": "x", "source": "s"}, headers=H).status_code == 404
    assert alice.get(f"/api/v1/projects/{pid}").json()["name"] == "p"


def test_task_ownership_and_memory_isolation(alice, bob, session_factory):
    pid, rid = new_run(alice)
    with session_factory() as s:  # tasks are written by the Scheduler: insert one directly
        s.add(Task(id="t-1", run_id=rid, type="build", assigned_agent="a"))
        s.commit()
    assert alice.get("/api/v1/tasks/t-1").status_code == 200 and bob.get("/api/v1/tasks/t-1").status_code == 404
    ok = alice.post("/api/v1/memory/", json={"project_id": pid, "content": "mine", "source": "s"}, headers=H)
    assert ok.status_code == 201
    assert [m["content"] for m in alice.get("/api/v1/memory/").json()] == ["mine"] and bob.get("/api/v1/memory/").json() == []


def test_legacy_unowned_projects_are_invisible_to_everyone(alice, session_factory):
    with session_factory() as s:
        s.add(Project(id="legacy-1", name="old", owner="x", goal_summary="g"))
        s.commit()
    assert alice.get("/api/v1/projects/").json() == [] and alice.get("/api/v1/projects/legacy-1").status_code == 404


def test_cost_summary_only_covers_my_runs(alice, bob, session_factory):
    _, run_a = new_run(alice)
    _, run_b = new_run(bob)
    with session_factory() as s:
        for rid, cost in ((run_a, 1.5), (run_b, 9.0)):
            tid = f"t-{rid[:8]}"
            s.add(Task(id=tid, run_id=rid, type="build", assigned_agent="a"))
            s.flush()
            s.add(AgentLog(id=f"log-{rid[:8]}", run_id=rid, task_id=tid, agent="queen", prompt_tokens=1, completion_tokens=1,
                           cost_usd=cost, latency_ms=1, outcome="ok", model="m"))
        s.commit()
    assert alice.get("/api/v1/agent-logs/cost-summary").json()["total_cost_usd"] == 1.5


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/v1/events/", {"run_id": "{r}", "event_type": "run.completed"}),
    ("patch", "/api/v1/runs/{r}", {"status": "completed"}),
    ("post", "/api/v1/tasks/", {"run_id": "{r}", "type": "build", "assigned_agent": "a"}),
    ("get", "/api/v1/workflow/stale", None), ("get", "/health/metrics", None),
])
def test_internal_endpoints_are_administrators_only(alice, session_factory, method, path, body):
    _, rid = new_run(alice)
    url = path.format(r=rid)
    kw = {"json": {k: v.format(r=rid) if isinstance(v, str) else v for k, v in body.items()}} if body is not None else {}
    denied = getattr(alice, method)(url, headers=H, **kw)
    assert denied.status_code == 403 and denied.json() == {"detail": "Administrator access required"}
    make_admin(session_factory, "alice@example.com")
    assert getattr(alice, method)(url, headers=H, **kw).status_code in (200, 201, 422)


# ══ CSRF / CORS / Origin ═════════════════════════════════════════════════


def test_cookie_authenticated_writes_need_a_trusted_origin(alice):
    body = {"name": "p", "owner": "o", "goal_summary": "g"}
    assert alice.post("/api/v1/projects/", json=body).status_code == 403                                   # no Origin
    assert alice.post("/api/v1/projects/", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert alice.post("/api/v1/projects/", json=body, headers={"Origin": "null"}).status_code == 403
    assert alice.post("/api/v1/projects/", json=body, headers=H).status_code == 201
    assert alice.get("/api/v1/projects/", headers={"Origin": "https://evil.example"}).status_code == 200  # reads: no CSRF risk


def test_bearer_clients_do_not_need_an_origin(make_client, alice):
    token = alice.cookies.get("hm_session")
    r = make_client().post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"},
                           headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_cors_allows_only_configured_origins_and_narrow_methods(make_client):
    c = make_client()
    ok = c.options("/api/v1/projects/", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN and ok.headers.get("access-control-allow-credentials") == "true"
    for evil in ("https://evil.example", "null", "http://localhost:3000.evil.example"):
        r = c.options("/api/v1/projects/", headers={"Origin": evil, "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in r.headers
    bad_method = c.options("/api/v1/projects/", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PUT"})
    assert bad_method.status_code == 400


# ══ WebSocket security (+ Phase 4 reliability preserved) ═════════════════


@pytest.fixture
def ws_api(session_factory, bus):
    def override_get_db():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_bus] = lambda: bus
    with TestClient(app) as client:  # real lifespan: hub + LISTEN thread
        assert app.state.telemetry_listener.connected.wait(10)
        yield client


def _ws_user(ws_api, email):
    c = TestClient(app)
    c.__enter__ = None  # noqa: no lifespan for the helper clients
    assert register(c, email).status_code == 201
    return c


def _connect(ws_api, run_id, cookie=None, headers=None, query=""):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = f"hm_session={cookie}"
    return ws_api.websocket_connect(f"/ws/runs/{run_id}{query}", headers=h)


def test_websocket_requires_authentication_ownership_and_a_trusted_origin(ws_api):
    a, b = TestClient(app), TestClient(app)
    register(a, "wa@example.com"), register(b, "wb@example.com")
    _, run_id = new_run(a)
    tok_a, tok_b = a.cookies.get("hm_session"), b.cookies.get("hm_session")

    with pytest.raises(WebSocketDisconnect):                       # anonymous: refused at the handshake
        with _connect(ws_api, run_id, headers=H):
            pass
    with pytest.raises(WebSocketDisconnect):                       # garbage token
        with _connect(ws_api, run_id, cookie="not.a.jwt", headers=H):
            pass
    with pytest.raises(WebSocketDisconnect):                       # valid user, hostile Origin
        with _connect(ws_api, run_id, cookie=tok_a, headers={"Origin": "https://evil.example"}):
            pass
    with pytest.raises(WebSocketDisconnect):                       # valid user, Origin "null"
        with _connect(ws_api, run_id, cookie=tok_a, headers={"Origin": "null"}):
            pass

    with _connect(ws_api, run_id, cookie=tok_b, headers=H) as ws:  # someone else's run: same close as an unknown run
        assert ws.receive()["code"] == 4404
    with _connect(ws_api, "does-not-exist", cookie=tok_b, headers=H) as ws:
        assert ws.receive()["code"] == 4404

    with _connect(ws_api, run_id, cookie=tok_a, headers=H) as ws:  # owner: accepted, gets the snapshot
        snap = ws.receive_json()
        assert snap["type"] == "workflow.snapshot" and snap["run_id"] == run_id
    with _connect(ws_api, run_id, headers={"Authorization": f"Bearer {tok_a}"}) as ws:  # non-browser client
        assert ws.receive_json()["type"] == "workflow.snapshot"


def test_websocket_reconnect_and_cursor_replay_still_work_when_authenticated(ws_api, bus, session_factory, monkeypatch):
    fakes.install_fake_agents(monkeypatch)
    sched = SchedulerConsumer("unused", "t", "g", consumer=object(), event_bus=bus, session_factory=session_factory)
    a = TestClient(app)
    register(a, "wr@example.com")
    _, run_id = new_run(a)
    tok = a.cookies.get("hm_session")
    i = 0
    while i < 3:  # three events consumed, then the browser "disconnects"
        sched.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
    with _connect(ws_api, run_id, cookie=tok, headers=H) as ws:
        first = ws.receive_json()
        assert first["mode"] == "full" and len(first["events"]) == 3
        cursor = first["last_event_id"]
    while i < len(bus.published):  # the run continues while nobody is connected
        sched.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
    with _connect(ws_api, run_id, cookie=tok, headers=H, query=f"?last_event_id={cursor}") as ws:
        resumed = ws.receive_json()
        seen = {e["event_id"] for e in first["events"]}
        assert resumed["mode"] == "resume" and resumed["events"] and not seen & {e["event_id"] for e in resumed["events"]}
        assert resumed["state"]["status"] == "completed"


# ══ rate limiting ════════════════════════════════════════════════════════


def test_login_is_rate_limited_per_client_and_below_the_limit_still_works(make_client, alice, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_PER_MIN", 3)
    c = make_client()
    good = {"email": "alice@example.com", "password": PASSWORD}
    assert [c.post("/api/v1/auth/login", json=good).status_code for _ in range(3)] == [200, 200, 200]
    limited = c.post("/api/v1/auth/login", json=good)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1


def test_registration_and_run_creation_are_rate_limited(make_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER_PER_HOUR", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_RUNS_PER_HOUR", 2)
    c = make_client()
    assert register(c, "r1@example.com").status_code == 201
    assert register(make_client(), "r2@example.com").status_code == 201
    assert register(make_client(), "r3@example.com").status_code == 429
    pid = c.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}, headers=H).json()["id"]
    codes = [c.post("/api/v1/runs/", json={"project_id": pid, "goal": "g"}, headers=H).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_memory_insertion_is_rate_limited_per_user(alice, bob, monkeypatch):
    pid, _ = new_run(alice)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_MEMORY_PER_MIN", 2)
    body = {"project_id": pid, "content": "c", "source": "s"}
    assert [alice.post("/api/v1/memory/", json=body, headers=H).status_code for _ in range(3)] == [201, 201, 429]
    pid_b, _ = new_run(bob)  # another user has their own budget
    assert bob.post("/api/v1/memory/", json={**body, "project_id": pid_b}, headers=H).status_code == 201


def test_rate_limiting_can_be_disabled(make_client, alice, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_PER_MIN", 1)  # RATE_LIMIT_ENABLED is False (fixture)
    c = make_client()
    assert all(c.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200
               for _ in range(4))


# ══ input validation ═════════════════════════════════════════════════════


def test_oversized_bodies_are_rejected_declared_or_streamed(alice, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BYTES", 2000)
    big = {"name": "p", "owner": "o", "goal_summary": "g" * 5000}
    assert alice.post("/api/v1/projects/", json=big, headers=H).status_code == 413

    def chunks():  # no Content-Length: chunked upload
        for _ in range(10):
            yield b"x" * 500
    assert alice.post("/api/v1/projects/", content=chunks(), headers={**H, "Content-Type": "application/json"}).status_code == 413
    assert alice.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}, headers=H).status_code == 201


@pytest.mark.parametrize("query", ["limit=0", "limit=100000", "limit=abc", "offset=-1", "offset=99999999999"])
def test_pagination_is_bounded(alice, query):
    assert alice.get(f"/api/v1/projects/?{query}").status_code == 422


def test_pagination_limits_results(alice):
    for _ in range(3):
        alice.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}, headers=H)
    assert len(alice.get("/api/v1/projects/?limit=2").json()) == 2 and len(alice.get("/api/v1/projects/?limit=2&offset=2").json()) == 1


@pytest.mark.parametrize("path,body", [
    ("/api/v1/projects/", {"name": "", "owner": "o", "goal_summary": "g"}),
    ("/api/v1/projects/", {"name": "n" * 256, "owner": "o", "goal_summary": "g"}),
    ("/api/v1/memory/", {"project_id": "p", "content": "x" * 5001, "source": "s"}),
    ("/api/v1/memory/", {"project_id": "p", "content": "x", "source": "s", "embedding_dimensions": 0}),
    ("/api/v1/memory/", {"project_id": "p", "content": "x", "source": "s", "embedding_dimensions": 99999}),
    ("/api/v1/runs/", {"project_id": "p" * 40, "goal": "g"}),
    ("/api/v1/runs/", {"project_id": "p", "goal": "g" * 5001}),
    ("/api/v1/runs/", {"project_id": "p", "goal": ""}),
])
def test_field_lengths_and_ranges_are_validated(alice, path, body):
    assert alice.post(path, json=body, headers=H).status_code == 422


def test_invalid_enum_for_run_status_and_invalid_ids(alice, session_factory):
    _, rid = new_run(alice)
    make_admin(session_factory, "alice@example.com")
    assert alice.patch(f"/api/v1/runs/{rid}", json={"status": "hacked"}, headers=H).status_code == 422
    assert alice.get("/api/v1/runs/" + "x" * 500).status_code == 404
    assert alice.get("/api/v1/events/?run_id=" + "x" * 40).status_code == 422
    assert alice.get("/api/v1/events/recent?limit=101").status_code == 422


def test_sql_injection_shaped_ids_are_inert(alice):
    for evil in ("' OR '1'='1", "1; DROP TABLE users;--", "%' UNION SELECT * FROM users--"):
        assert alice.get(f"/api/v1/runs/{evil}").status_code == 404
        assert alice.get("/api/v1/projects/", params={"limit": "1; DROP TABLE users"}).status_code == 422
    assert alice.get("/api/v1/auth/me").status_code == 200


# ══ error / secret hygiene, headers, request ids ═════════════════════════


def test_security_headers_and_request_id_on_every_response(make_client):
    r = make_client().get("/health/live", headers={"X-Request-ID": "trace-12345678"})
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in h["content-security-policy"] and h["cache-control"] == "no-store"
    assert h["x-request-id"] == "trace-12345678"
    assert make_client().get("/health/live", headers={"X-Request-ID": "bad id\n<script>"}).headers["x-request-id"] != "bad id"


def test_unhandled_errors_never_expose_internals(make_client, caplog):
    @app.get("/_boom")
    def boom():
        raise RuntimeError("secret-internal-detail postgresql://user:pw@db/x C:\\srv\\app.py")

    try:
        c = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.ERROR):
            r = c.get("/_boom")
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/_boom"]
    assert r.status_code == 500 and set(r.json()) == {"detail", "request_id"} and r.json()["detail"] == "Internal server error"
    assert "secret-internal" not in r.text and "postgresql" not in r.text and "Traceback" not in r.text
    assert "secret-internal-detail" not in r.text and r.headers["x-request-id"] == r.json()["request_id"]


def test_secrets_never_reach_api_responses(alice, make_client, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_" + "A1b2C3d4E5f6G7h8I9j0K1l2")
    monkeypatch.setattr(settings, "FEATHERLESS_API_KEY", "fl_" + "Z9y8X7w6V5u4T3s2R1q0P9o8")
    bodies = [alice.get(p).text for p in ("/api/v1/auth/me", "/api/v1/system/services", "/api/v1/system/agents",
                                          "/health/", "/health/live", "/health/ready")]
    blob = " ".join(bodies)
    for secret in (settings.GROQ_API_KEY, settings.FEATHERLESS_API_KEY, settings.JWT_SECRET, "password_hash", "argon2"):
        assert secret not in blob


def test_credentials_and_tokens_are_never_logged(make_client, caplog):
    with caplog.at_level(logging.DEBUG):
        c = make_client()
        register(c, "log@example.com", password="super-secret-passphrase-1")
        token = c.cookies.get("hm_session")
        c.post("/api/v1/auth/login", json={"email": "log@example.com", "password": "wrong-passphrase-2"})
        c.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
        c.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.value"})
    text_out = caplog.text
    for secret in ("super-secret-passphrase-1", "wrong-passphrase-2", token, "bad.token.value"):
        assert secret not in text_out


def test_validation_errors_do_not_echo_submitted_values(make_client):
    r = make_client().post("/api/v1/auth/login", json={"email": "a@b.co", "password": ["leak-me-please"]})
    assert r.status_code == 422 and "leak-me-please" not in r.text


# ══ health / readiness ═══════════════════════════════════════════════════


def test_liveness_checks_no_dependency_readiness_checks_database_and_kafka(make_client):
    c = make_client()
    assert c.get("/health/live").status_code == 200
    app.state.event_bus = type("B", (), {"producer": type("P", (), {"list_topics": lambda self, **k: object()})()})()
    try:
        r = c.get("/health/ready")
        assert r.status_code == 200 and r.json() == {"status": "ready", "checks": {"database": "ok", "kafka": "ok"}}

        class Broken:
            def list_topics(self, **k):
                raise RuntimeError("broker down at kafka-internal:9092")
        app.state.event_bus.producer = Broken()
        r = c.get("/health/ready")
        assert r.status_code == 503 and r.json()["checks"] == {"database": "ok", "kafka": "unavailable"}
        assert "kafka-internal" not in r.text  # no infrastructure details
    finally:
        del app.state.event_bus


# ══ operator CLI ═════════════════════════════════════════════════════════


def test_cli_creates_admins_and_adopts_legacy_projects(session_factory, monkeypatch):
    from app import cli
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    with session_factory() as s:
        s.add(Project(id="legacy-2", name="old", owner="x", goal_summary="g"))
        s.commit()
    assert "created" in cli.create_admin("Ops@Example.com", "a-long-admin-password")
    assert "promoted" in cli.create_admin("ops@example.com", "another-long-password")
    with pytest.raises(SystemExit):
        cli.create_admin("x@example.com", "short")
    assert "1 unowned project" in cli.adopt_legacy_projects("ops@example.com")
    with session_factory() as s:
        ops = s.scalar(select(User).where(User.email == "ops@example.com"))
        assert ops.is_admin and s.get(Project, "legacy-2").owner_id == ops.id
