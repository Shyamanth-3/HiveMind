"""
Phase 4 WebSocket telemetry tests. Real PostgreSQL; the Scheduler (in this process) commits events, sends
NOTIFY, the real listener thread wakes the real hub, and Starlette's TestClient plays the browser. Fake agents,
fake Kafka bus (real Kafka is covered in test_e2e_kafka.py). No LLM.
"""

import asyncio
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.dependencies import get_event_bus
from app.db.database import get_db
from app.events.schemas import KafkaEvent
from app.main import app
from app.models import Event, Run
from app.scheduler import consumer as consumer_mod
from app.scheduler.consumer import SchedulerConsumer
from app.telemetry import store
from app.telemetry.contract import summarize_payload, valid_id
from app.telemetry.hub import TelemetryHub
from tests import fakes

HAPPY = ["run.created", "strategy.created", "architecture.created", "research.completed",
         "tasks.generated", "review.completed", "run.completed"]


# ── harness ─────────────────────────────────────────────────────────────


@pytest.fixture
def scheduler(monkeypatch, bus, session_factory):
    fakes.install_fake_agents(monkeypatch)
    return SchedulerConsumer("unused", "t", "g", consumer=object(), event_bus=bus, session_factory=session_factory)


@pytest.fixture
def api(session_factory, bus):
    """The real app with its real lifespan (hub + LISTEN thread), REST deps pointed at the test DB/fake bus."""
    def override_get_db():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_bus] = lambda: bus
    with TestClient(app) as client:
        assert app.state.telemetry_listener.connected.wait(10), "LISTEN connection did not come up"
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def run_id(api):
    pid = api.post("/api/v1/projects/", json={"name": "p", "owner": "o", "goal_summary": "g"}).json()["id"]
    return api.post("/api/v1/runs/", json={"project_id": pid, "goal": "Build a thing"}).json()["id"]


@pytest.fixture
def second_run_id(api):
    pid = api.post("/api/v1/projects/", json={"name": "p2", "owner": "o", "goal_summary": "g"}).json()["id"]
    return api.post("/api/v1/runs/", json={"project_id": pid, "goal": "Another thing"}).json()["id"]


class Browser:
    """A WebSocket session with receive timeouts (TestClient's own receive would block forever)."""

    def __init__(self, session):
        self.session, self._pool = session, ThreadPoolExecutor(max_workers=1)

    def recv(self, timeout=10.0):
        return self._pool.submit(self.session.receive_json).result(timeout)

    def until(self, predicate, timeout=20.0):
        """Collect messages until `predicate(msg)`; returns all of them (including the matching one)."""
        out, deadline = [], time.time() + timeout
        while time.time() < deadline:
            msg = self.recv(max(0.1, deadline - time.time()))
            out.append(msg)
            if predicate(msg):
                return out
        raise AssertionError(f"predicate never matched; got {[m.get('type') for m in out]}")


@contextmanager
def open_ws(api, run_id, last_event_id=None, headers=None):
    """Connect like a browser. Closes explicitly on exit: TestClient's own __exit__ cancels the app task instead of
    delivering websocket.disconnect the way uvicorn does (real disconnects are verified against uvicorn live)."""
    url = f"/ws/runs/{run_id}" + (f"?last_event_id={last_event_id}" if last_event_id else "")
    hub = app.state.telemetry_hub
    with api.websocket_connect(url, headers=headers or {}) as session:
        try:
            yield session
        finally:
            before = hub.client_count()
            try:
                session.close(1000)
            except Exception:
                pass
            if before:  # give the app one loop turn to process the disconnect before TestClient cancels it
                wait_until(lambda: hub.client_count() < before, 2.0)


def feed(scheduler, bus, start=0, limit=None):
    """Deliver published events to the scheduler like Kafka would; stop after `limit` events."""
    i, done = start, 0
    while i < len(bus.published) and (limit is None or done < limit):
        scheduler.process(KafkaEvent.model_validate_json(bus.published[i].to_json_bytes()))
        i += 1
        done += 1
    return i


def wait_until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def event_types(msgs):
    return [m["event_type"] for m in msgs if m["type"] == "workflow.event"]


def is_state(status=None):
    return lambda m: m["type"] == "workflow.state" and (status is None or m["state"]["status"] == status)


# ── connection ──────────────────────────────────────────────────────────


def test_connect_sends_a_full_snapshot_and_disconnect_cleans_up(api, run_id):
    hub = app.state.telemetry_hub
    with open_ws(api, run_id) as s:
        snap = Browser(s).recv()
        assert snap["type"] == "workflow.snapshot" and snap["mode"] == "full" and snap["run_id"] == run_id
        assert snap["events"] == [] and snap["state"]["status"] == "running" and snap["last_event_id"] is None
        assert snap["state"]["agents"]["queen"]["status"] == "running"  # nothing consumed yet: the Queen has it
        assert wait_until(lambda: hub.client_count(run_id) == 1)
    assert wait_until(lambda: hub.client_count() == 0)  # removed after the socket closed


@pytest.mark.parametrize("bad", ["does-not-exist", "run_999"])
def test_unknown_run_is_closed_with_4404(api, bad):
    with open_ws(api, bad) as s:
        with pytest.raises(WebSocketDisconnect) as e:
            s.receive_json()
        assert e.value.code == 4404


@pytest.mark.parametrize("bad", ["x" * 70, "a b", "a;drop", "a.b", "%27OR%271"])
def test_malformed_run_ids_are_rejected_before_any_database_access(api, bad, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("database must not be touched for a malformed id")
    monkeypatch.setattr(app.state.telemetry_hub, "_snapshot", boom)
    with open_ws(api, bad) as s:
        with pytest.raises(WebSocketDisconnect) as e:
            s.receive_json()
        assert e.value.code == 4400


def test_malformed_last_event_id_is_rejected(api, run_id):
    with open_ws(api, run_id, last_event_id="x;y") as s:
        with pytest.raises(WebSocketDisconnect) as e:
            s.receive_json()
        assert e.value.code == 4400


def test_origin_is_checked_for_browser_clients(api, run_id):
    allowed = settings.cors_origin_list[0]
    with pytest.raises(WebSocketDisconnect) as e:
        with open_ws(api, run_id, headers={"origin": "https://evil.example"}):
            pass
    assert e.value.code == 1008
    with open_ws(api, run_id, headers={"origin": allowed}) as s:   # configured origin
        assert Browser(s).recv()["type"] == "workflow.snapshot"
    with open_ws(api, run_id) as s:                                # non-browser client: no Origin header
        assert Browser(s).recv()["type"] == "workflow.snapshot"


def test_ping_is_answered_with_pong_and_garbage_is_ignored(api, run_id):
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        s.send_text("not json")
        s.send_json({"type": "ping"})
        assert b.recv()["type"] == "pong"


def test_heartbeat_is_sent_periodically(api, run_id, monkeypatch):
    monkeypatch.setattr(app.state.telemetry_hub, "heartbeat_s", 0.2)
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        assert b.until(lambda m: m["type"] == "heartbeat", timeout=5)[-1]["ts"]


# ── subscription / live broadcast ───────────────────────────────────────


def test_live_events_arrive_in_order_only_after_their_commit(api, scheduler, bus, run_id, session_factory):
    with open_ws(api, run_id) as s:
        b = Browser(s)
        assert b.recv()["type"] == "workflow.snapshot"
        threading.Thread(target=feed, args=(scheduler, bus), daemon=True).start()
        msgs = b.until(is_state("completed"))
        assert event_types(msgs) == HAPPY
        with session_factory() as db:  # every event the browser saw is durably persisted (and only then was sent)
            persisted = {e.id for e in db.scalars(select(Event).where(Event.run_id == run_id))}
        assert {m["event_id"] for m in msgs if m["type"] == "workflow.event"} == persisted
        final = msgs[-1]["state"]
        assert final["status"] == "completed" and final["is_completed"] and final["current_stage"] is None
        assert all(a["status"] == "completed" for a in final["agents"].values())
        assert final["failure"] is None and final["last_event_id"] == msgs[-2]["event_id"]


def test_events_are_only_sent_to_subscribers_of_that_run(api, scheduler, bus, run_id, second_run_id):
    with open_ws(api, run_id) as a1, open_ws(api, run_id) as a2, open_ws(api, second_run_id) as other:
        ba1, ba2, bo = Browser(a1), Browser(a2), Browser(other)
        for b in (ba1, ba2, bo):
            assert b.recv()["type"] == "workflow.snapshot"
        first_run_created = next(e for e in bus.published if e.run_id == run_id)
        threading.Thread(target=lambda: scheduler.process(first_run_created), daemon=True).start()
        for b in (ba1, ba2):                                   # both tabs of run A get it
            msgs = b.until(lambda m: m["type"] == "workflow.state")
            assert event_types(msgs) == ["run.created"] and msgs[0]["run_id"] == run_id
        with pytest.raises(Exception):                         # run B's tab gets nothing
            bo.recv(timeout=1.5)


def test_hub_subscribe_unsubscribe_and_broadcast_bookkeeping(api, run_id, second_run_id):
    hub = app.state.telemetry_hub
    with open_ws(api, run_id) as a, open_ws(api, run_id) as b, open_ws(api, second_run_id) as c:
        for s in (a, b, c):
            Browser(s).recv()
        assert wait_until(lambda: hub.client_count() == 3)
        assert hub.client_count(run_id) == 2 and hub.client_count(second_run_id) == 1
        assert sorted(hub.run_ids()) == sorted([run_id, second_run_id])
        assert hub.broadcast_to_run(run_id, {"type": "maintenance"}) == 2
        assert hub.broadcast({"type": "maintenance"}) == 3
    assert wait_until(lambda: hub.client_count() == 0)


# ── snapshot + recovery ─────────────────────────────────────────────────


def test_snapshot_matches_the_rest_status(api, scheduler, bus, run_id):
    feed(scheduler, bus, limit=3)   # consumed: run.created, strategy.created, architecture.created
    rest = api.get(f"/api/v1/workflow/{run_id}/status").json()
    with open_ws(api, run_id) as s:
        snap = Browser(s).recv()
    assert event_types(snap["events"]) == HAPPY[:3]
    st = snap["state"]
    assert (st["status"], st["current_stage"], st["last_event_id"]) == (rest["status"], rest["current_stage"], rest["last_event_id"])
    assert st["agents"] == rest["agents"] and st["revision"]["count"] == rest["revision_count"]
    # three events persisted = Queen, Architect and Scout have finished consuming; the Builder is working now
    assert [st["agents"][a]["status"] for a in ("queen", "architect", "scout", "builder", "guardian")] == \
           ["completed", "completed", "completed", "running", "pending"]


def test_missed_events_are_recovered_after_a_disconnect_without_duplicates(api, scheduler, bus, run_id):
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        threading.Thread(target=feed, args=(scheduler, bus), kwargs={"limit": 2}, daemon=True).start()
        seen = b.until(lambda m: m.get("event_type") == "strategy.created")
        last_seen = seen[-1]["event_id"]
    # the browser is gone: events 3..7 happen now
    feed(scheduler, bus, start=2)
    with open_ws(api, run_id, last_event_id=last_seen) as s2:
        snap = Browser(s2).recv()
    assert snap["mode"] == "resume"
    assert event_types(snap["events"]) == HAPPY[2:]                      # exactly the missed events
    ids = [m["event_id"] for m in seen if m["type"] == "workflow.event"] + [e["event_id"] for e in snap["events"]]
    assert len(ids) == len(set(ids)) == len(HAPPY)                       # nothing lost, nothing twice
    assert snap["state"]["status"] == "completed" and snap["last_event_id"] == snap["events"][-1]["event_id"]


def test_resume_then_live_continues_without_a_gap(api, scheduler, bus, run_id):
    feed(scheduler, bus, limit=2)
    with open_ws(api, run_id) as s:
        first = Browser(s).recv()
    last = first["last_event_id"]
    feed(scheduler, bus, start=2, limit=2)                                # while disconnected
    with open_ws(api, run_id, last_event_id=last) as s2:
        b = Browser(s2)
        snap = b.recv()
        assert event_types(snap["events"]) == HAPPY[2:4]
        threading.Thread(target=feed, args=(scheduler, bus), kwargs={"start": 4}, daemon=True).start()
        live = b.until(is_state("completed"))
        assert event_types(live) == HAPPY[4:]


@pytest.mark.parametrize("bad", ["unknown-event", "evt_does_not_exist"])
def test_unknown_last_event_id_falls_back_to_full_history(api, scheduler, bus, run_id, bad):
    feed(scheduler, bus, limit=2)
    with open_ws(api, run_id, last_event_id=bad) as s:
        snap = Browser(s).recv()
    assert snap["mode"] == "full" and event_types(snap["events"]) == HAPPY[:2]


def test_last_event_id_of_another_run_is_not_honoured(api, scheduler, bus, run_id, second_run_id):
    feed(scheduler, bus)  # both runs' run.created are in bus.published; processes everything for both
    with open_ws(api, second_run_id) as s:
        other_last = Browser(s).recv()["last_event_id"]
    with open_ws(api, run_id, last_event_id=other_last) as s:
        snap = Browser(s).recv()
    assert snap["mode"] == "full" and all(e["run_id"] == run_id for e in snap["events"])


# ── revision + failure telemetry ────────────────────────────────────────


def test_revision_is_visible_in_events_and_agent_states(api, scheduler, bus, run_id):
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        threading.Thread(target=feed, args=(scheduler, bus), daemon=True).start()
        msgs = b.until(is_state("completed"))
    types = event_types(msgs)
    assert types == HAPPY[:6] + ["revision.requested", "tasks.generated", "review.completed", "run.completed"]
    req = next(m for m in msgs if m.get("event_type") == "revision.requested")
    assert req["revision_number"] == 1 and req["payload"]["max_revisions"] == settings.MAX_REVISIONS
    assert req["payload"]["feedback"] == ["architecture: add deployment detail"]
    assert req["payload"]["requested_changes"] == 2 and "Add a deployment task" in req["payload"]["requested_changes_preview"]
    reviews = [m for m in msgs if m.get("event_type") == "review.completed"]
    assert [r["payload"]["verdict"] for r in reviews] == ["needs_revision", "approved"]
    states = [m["state"] for m in msgs if m["type"] == "workflow.state"]
    assert any(st["agents"]["guardian"]["status"] == "revision" for st in states)               # needs revision shown
    assert any(st["agents"]["builder"]["status"] == "running" and st["agents"]["builder"]["revision"] == 1
               for st in states)                                                                  # Builder revising
    assert states[-1]["revision"] == {"count": 1, "max": settings.MAX_REVISIONS, "current": 1, "status": "approved"}
    assert all(st["status"] == "running" for st in states[:-1])                                    # never "completed" early


def test_run_failed_is_sent_with_a_safe_failure_summary(api, scheduler, bus, run_id, monkeypatch):
    class Leaky(fakes.FakeScout):
        async def generate_research(self, *a, **k):
            raise RuntimeError("boom sk-abcdefghijklmnopqrstuvwxyz0123456789 " + "x" * 600)

    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        monkeypatch.setattr(consumer_mod, "ScoutService", Leaky)
        threading.Thread(target=feed, args=(scheduler, bus), daemon=True).start()
        msgs = b.until(is_state("failed"))
    failed = next(m for m in msgs if m.get("event_type") == "run.failed")
    assert failed["payload"]["failed_stage"] == "scout" and failed["payload"]["error_type"] == "RuntimeError"
    assert "sk-abcdef" not in str(msgs) and len(failed["payload"]["message"]) <= 240
    assert set(failed["payload"]) == {"failed_stage", "error_type", "message", "verdict", "revision_count", "max_revisions"}
    st = msgs[-1]["state"]
    assert st["status"] == "failed" and st["agents"]["scout"]["status"] == "failed" and st["agents"]["builder"]["status"] == "pending"
    assert st["failure"]["failed_stage"] == "scout"


def test_max_revisions_failure_is_shown_as_a_failed_run_not_a_disconnect(api, scheduler, bus, run_id, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REVISIONS", 1)
    fakes.VERDICT[:] = ["needs_revision"]
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        threading.Thread(target=feed, args=(scheduler, bus), daemon=True).start()
        msgs = b.until(is_state("failed"))
    assert msgs[-1]["state"]["failure"]["error_type"] == "MAX_REVISIONS_EXCEEDED"
    assert msgs[-1]["state"]["revision"]["count"] == 1


def test_payloads_are_summaries_never_raw_kafka_payloads_or_prompts(scheduler, bus, run_id, session_factory):
    feed(scheduler, bus)
    with session_factory() as db:
        for e in db.scalars(select(Event).where(Event.run_id == run_id)):
            summary = summarize_payload(e.event_type, e.payload)
            blob = str(summary)
            for raw_key in ("architecture_plan", "research_report", "task_graph", "validation_report", "strategy"):
                assert raw_key not in summary, f"{e.event_type} leaks {raw_key}"
            assert "Task 1" not in blob                                   # task titles are not in the summary either
    assert summarize_payload("tasks.generated", {"task_graph": {"summary": "s", "tasks": [1, 2, 3]}}) == \
           {"summary": "s", "task_count": 3, "revision_number": 0}
    assert summarize_payload("strategy.created", {"strategy": {"summary": "key is gsk_abcdefghijklmnopqrstuvwxyz012345",
                                                               "phases": []}})["summary"] == "[redacted]"
    assert summarize_payload("unknown.event", {"a": 1}) == {}


def test_provider_account_ids_are_scrubbed_from_failure_messages():
    msg = ("Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization "
           "`org_01kpv66neyfms9n74b4e1xbsr3` service tier `on_demand` on tokens per day (TPD)', 'request': 'req_01abcdefghijkl'}}")
    out = summarize_payload("run.failed", {"failed_stage": "scout", "error_type": "RateLimitError", "message": msg})
    assert "org_01kpv66" not in out["message"] and "req_01abc" not in out["message"]
    assert "org_…" in out["message"] and "Rate limit reached" in out["message"]   # still useful to a human


def test_id_validation():
    assert all(valid_id(x) for x in ["run_001", "5f98da5c-b557-4d42-bc27-dff6e2f57a3c", "a" * 64])
    assert not any(valid_id(x) for x in [None, "", "a" * 65, "a b", "a/b", "a;b", "é"])


# ── failure isolation: telemetry problems never touch the workflow ──────


def _statuses(session_factory, run_id):
    with session_factory() as db:
        return db.get(Run, run_id).status


def test_notify_failure_never_affects_the_workflow(scheduler, bus, run_id, session_factory, monkeypatch):
    """pg_notify blows up after EVERY commit: tasks.generated, review.completed, revision.requested, run.completed all still work."""
    def broken_text(*a, **k):
        raise RuntimeError("notify is broken")
    monkeypatch.setattr(consumer_mod, "text", broken_text)
    fakes.VERDICT[:] = ["needs_revision", "approved"]
    feed(scheduler, bus)
    assert _statuses(session_factory, run_id) == "completed"
    with session_factory() as db:
        types = [e.event_type for e in db.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.created_at))]
    assert types == HAPPY[:6] + ["revision.requested", "tasks.generated", "review.completed", "run.completed"]


def test_notify_failure_on_the_failure_path_still_marks_the_run_failed(scheduler, bus, run_id, session_factory, monkeypatch):
    monkeypatch.setattr(consumer_mod, "text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no notify")))
    fakes.FAIL_STAGE.append("scout")
    feed(scheduler, bus)
    assert _statuses(session_factory, run_id) == "failed"


def test_hub_errors_never_reach_the_scheduler(api, scheduler, bus, run_id, session_factory, monkeypatch):
    """A connected browser + a hub that raises while delivering: the run still completes, and REST still tells the truth."""
    def boom(*a, **k):
        raise RuntimeError("hub exploded")
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        monkeypatch.setattr(app.state.telemetry_hub, "_updates", boom)
        feed(scheduler, bus)
        assert _statuses(session_factory, run_id) == "completed"
    assert api.get(f"/api/v1/workflow/{run_id}/status").json()["status"] == "completed"


def test_browser_closing_mid_run_does_not_disturb_processing(api, scheduler, bus, run_id, session_factory):
    with open_ws(api, run_id) as s:
        b = Browser(s)
        b.recv()
        feed(scheduler, bus, limit=2)
    feed(scheduler, bus, start=2)   # nobody is listening any more
    assert _statuses(session_factory, run_id) == "completed"


def test_scheduler_needs_no_websocket_infrastructure_at_all(scheduler, bus, run_id, session_factory):
    feed(scheduler, bus)   # no API app, no hub, no listener in this test: notify is just an unheard NOTIFY
    assert _statuses(session_factory, run_id) == "completed"


# ── backpressure (hub-level, fake sockets) ──────────────────────────────


class FakeSocket:
    """Minimal WebSocket stand-in. `stall` makes send_text block forever (a browser that stopped reading)."""

    def __init__(self, stall=False):
        self.stall, self.sent, self.closed_with = stall, [], None

    async def send_text(self, text):
        if self.stall:
            await asyncio.sleep(3600)
        self.sent.append(text)

    async def close(self, code=1000, reason=""):
        self.closed_with = code


def _commit_events(scheduler, bus, n):
    feed(scheduler, bus, limit=n)


@pytest.mark.anyio
async def test_a_slow_client_is_dropped_and_never_blocks_a_healthy_one(scheduler, bus, run_id, session_factory):
    hub = TelemetryHub(session_factory=session_factory, queue_size=3, send_timeout=30, heartbeat_s=3600)
    slow, fast = FakeSocket(stall=True), FakeSocket()
    c_slow = await hub.connect(slow, run_id)
    c_fast_hub = TelemetryHub(session_factory=session_factory, queue_size=100, heartbeat_s=3600)
    c_fast = await c_fast_hub.connect(fast, run_id)
    assert c_slow is not None and c_fast is not None

    await asyncio.to_thread(_commit_events, scheduler, bus, 7)        # 7 events -> 8 messages for each client
    hub.notify_run(run_id)
    c_fast_hub.notify_run(run_id)
    await asyncio.sleep(1.0)

    assert slow.closed_with == 1013 and hub.dropped_slow >= 1 and hub.client_count() == 0   # slow client dropped
    got = [__import__("json").loads(t) for t in fast.sent]
    assert [m["event_type"] for m in got if m["type"] == "workflow.event"] == HAPPY   # healthy client got everything
    await c_fast_hub.close_all()


@pytest.mark.anyio
async def test_a_stalled_socket_is_dropped_after_the_send_timeout(scheduler, bus, run_id, session_factory):
    hub = TelemetryHub(session_factory=session_factory, queue_size=100, send_timeout=0.2, heartbeat_s=3600)
    sock = FakeSocket(stall=True)
    client = await hub.connect(sock, run_id)
    assert client is not None
    await asyncio.sleep(0.8)          # the snapshot send stalls -> timeout -> dropped
    assert hub.client_count() == 0 and client.closed


@pytest.mark.anyio
async def test_recovering_after_a_drop_uses_the_database_not_a_buffer(scheduler, bus, run_id, session_factory):
    hub = TelemetryHub(session_factory=session_factory, queue_size=3, send_timeout=30, heartbeat_s=3600)
    slow = FakeSocket(stall=True)
    await hub.connect(slow, run_id)
    await asyncio.to_thread(_commit_events, scheduler, bus, 7)
    hub.notify_run(run_id)
    await asyncio.sleep(0.5)
    assert hub.client_count() == 0                                     # dropped, and its queue is gone with it
    fresh = FakeSocket()
    await hub.connect(fresh, run_id)                                   # reconnect: full history straight from PostgreSQL
    await asyncio.sleep(0.3)
    snap = __import__("json").loads(fresh.sent[0])
    assert snap["type"] == "workflow.snapshot" and event_types(snap["events"]) == HAPPY
    await hub.close_all()


def test_store_cursor_ordering_and_scoping(scheduler, bus, run_id, second_run_id, session_factory):
    feed(scheduler, bus)
    with session_factory() as db:
        events = store.events_after(db, run_id, None)
        assert [e.event_type for e in events] == HAPPY
        cur = store.resolve_cursor(db, run_id, events[2].id)
        assert [e.event_type for e in store.events_after(db, run_id, cur)] == HAPPY[3:]
        assert store.resolve_cursor(db, second_run_id, events[2].id) is None   # another run's id: not honoured
        assert store.resolve_cursor(db, run_id, None) is None
