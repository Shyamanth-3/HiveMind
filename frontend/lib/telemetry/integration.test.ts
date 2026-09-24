// @vitest-environment node
// Real sockets: the production TelemetryClient + reducer against a real `ws` server that drops connections.
import { afterEach, describe, expect, it } from "vitest";
import { WebSocketServer, type WebSocket as ServerSocket } from "ws";
import { TelemetryClient } from "./client";
import { initialStreamState, reduce, type StreamState } from "./reducer";
import type { ConnectionState, ServerMessage } from "./types";

type Ev = { type: "workflow.event"; event_id: string; event_type: string; run_id: string; timestamp: string; source: null; revision_number: null; payload: object };

const ev = (n: number, t: string): Ev => ({
  type: "workflow.event", event_id: `e${n}`, event_type: t, run_id: "run-1",
  timestamp: new Date(2026, 8, 24, 10, 0, n).toISOString(), source: null, revision_number: null, payload: {},
});
const state = (status = "running") => ({
  run_id: "run-1", status, is_completed: status === "completed", current_stage: null,
  revision: { count: 0, max: 3, current: 0, status: "none" },
  agents: Object.fromEntries(["queen", "architect", "scout", "builder", "guardian"].map((a) => [a, { status: "pending", revision: 0 }])),
  failure: null, last_event_id: null,
});

class FakeBackend {
  history: Ev[] = [];
  urls: string[] = [];
  sockets = new Set<ServerSocket>();
  silent = false; // stop sending anything (simulates a dead link the OS has not noticed)
  wss!: WebSocketServer;
  port = 0;

  async start(port = 0) {
    this.wss = new WebSocketServer({ port, host: "127.0.0.1" });
    await new Promise<void>((r) => this.wss.once("listening", () => r()));
    this.port = (this.wss.address() as { port: number }).port;
    this.wss.on("connection", (sock, req) => {
      const url = req.url ?? "";
      this.urls.push(url);
      const m = url.match(/^\/ws\/runs\/([^?]+)(?:\?last_event_id=(.+))?$/);
      if (!m || m[1] === "missing") return sock.close(4404, "run not found");
      this.sockets.add(sock);
      sock.on("close", () => this.sockets.delete(sock));
      if (this.silent) return;
      const last = m[2];
      const idx = last ? this.history.findIndex((e) => e.event_id === last) : -1;
      const resume = idx >= 0;
      sock.send(JSON.stringify({
        type: "workflow.snapshot", mode: resume ? "resume" : "full", run_id: "run-1", state: state(),
        events: resume ? this.history.slice(idx + 1) : this.history, last_event_id: this.history.at(-1)?.event_id ?? null,
      }));
    });
  }
  publish(e: Ev) {
    this.history.push(e);
    if (this.silent) return;
    for (const s of this.sockets) {
      s.send(JSON.stringify(e));
      s.send(JSON.stringify({ type: "workflow.state", run_id: "run-1", state: state() }));
    }
  }
  drop() {
    for (const s of this.sockets) s.terminate(); // abrupt: no close frame, like a network failure
    this.sockets.clear();
  }
  async stop() {
    this.drop();
    await new Promise<void>((r) => this.wss.close(() => r()));
  }
}

const until = async (cond: () => boolean, ms = 4000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (cond()) return;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error("condition not met in time");
};

let backend: FakeBackend;
let client: TelemetryClient | null = null;
afterEach(async () => {
  client?.stop();
  client = null;
  await backend?.stop();
});

function connect(runId = "run-1", over: Record<string, unknown> = {}) {
  let s: StreamState = initialStreamState;
  const states: ConnectionState[] = [];
  const infos: { s: ConnectionState; nextRetryMs?: number }[] = [];
  client = new TelemetryClient({
    url: (last) => `ws://127.0.0.1:${backend.port}/ws/runs/${runId}${last ? `?last_event_id=${last}` : ""}`,
    getLastEventId: () => s.lastEventId,
    onMessage: (m: ServerMessage) => (s = reduce(s, { type: "message", message: m })),
    onConnectionState: (st, info) => {
      states.push(st);
      infos.push({ s: st, nextRetryMs: info?.nextRetryMs });
    },
    baseDelayMs: 40, maxDelayMs: 200, jitter: 0,
    ...over,
  });
  client.start();
  return { get: () => s, states, infos };
}

describe("TelemetryClient over real sockets", () => {
  it("streams live events, survives an abrupt drop, and recovers exactly the missed events", async () => {
    backend = new FakeBackend();
    await backend.start();
    backend.history.push(ev(1, "run.created"));
    const c = connect();
    await until(() => c.get().events.length === 1);

    backend.publish(ev(2, "strategy.created"));
    backend.publish(ev(3, "architecture.created"));
    await until(() => c.get().events.length === 3);

    backend.drop(); // the network dies
    await until(() => c.states.includes("reconnecting"));
    backend.publish(ev(4, "research.completed")); // happen while the client is away
    backend.publish(ev(5, "tasks.generated"));

    await until(() => c.get().events.length === 5); // reconnect + resume snapshot
    expect(c.get().events.map((e) => e.event_id)).toEqual(["e1", "e2", "e3", "e4", "e5"]);
    expect(backend.urls.at(-1)).toBe("/ws/runs/run-1?last_event_id=e3"); // resumed from the last applied event
    expect(c.states.at(-1)).toBe("connected");

    backend.publish(ev(6, "review.completed")); // and live delivery continues after the recovery
    await until(() => c.get().events.length === 6);
    expect(new Set(c.get().events.map((e) => e.event_id)).size).toBe(6);
  });

  it("recovers across several consecutive drops without duplicating anything", async () => {
    backend = new FakeBackend();
    await backend.start();
    backend.history.push(ev(1, "run.created"));
    const c = connect();
    await until(() => c.get().events.length === 1);
    for (let round = 0; round < 3; round++) {
      backend.drop();
      await until(() => c.states.at(-1) === "reconnecting");
      backend.publish(ev(2 + round * 2, "a"));
      backend.publish(ev(3 + round * 2, "b"));
      await until(() => c.get().events.length === 3 + round * 2);
    }
    expect(c.get().events.map((e) => e.event_id)).toEqual(["e1", "e2", "e3", "e4", "e5", "e6", "e7"]);
  });

  it("a server that re-sends events we already have (full snapshot) creates no duplicates", async () => {
    backend = new FakeBackend();
    await backend.start();
    backend.history.push(ev(1, "run.created"), ev(2, "strategy.created"));
    const c = connect();
    await until(() => c.get().events.length === 2);
    backend.history = [ev(9, "run.created")]; // server forgot the cursor: unknown id -> full snapshot of new history
    backend.drop();
    await until(() => c.get().events.some((e) => e.event_id === "e9"));
    expect(c.get().events.map((e) => e.event_id)).toEqual(["e9"]); // full snapshot replaced the history
  });

  it("an unknown run closes with 4404: error state, exactly one connection attempt", async () => {
    backend = new FakeBackend();
    await backend.start();
    const c = connect("missing");
    await until(() => c.states.includes("error"));
    await new Promise((r) => setTimeout(r, 400));
    expect(backend.urls).toHaveLength(1);
  });

  it("reconnects while the server is completely down, with growing delays, and recovers when it returns", async () => {
    backend = new FakeBackend();
    await backend.start();
    backend.history.push(ev(1, "run.created"));
    const c = connect();
    await until(() => c.get().events.length === 1);
    const port = backend.port;
    await backend.stop(); // server down
    await until(() => c.infos.filter((i) => i.s === "reconnecting" && i.nextRetryMs !== undefined).length >= 3, 6000)
      .catch(() => { throw new Error("never saw 3 retries: " + JSON.stringify(c.infos)); });
    const delays = c.infos.filter((i) => i.nextRetryMs !== undefined).map((i) => i.nextRetryMs!);
    expect(delays.slice(0, 3)).toEqual([40, 80, 160]); // bounded exponential backoff, no reconnect storm
    const revived = new FakeBackend();
    revived.history = [ev(1, "run.created"), ev(2, "strategy.created")];
    await revived.start(port);
    backend = revived;
    await until(() => c.get().events.length === 2, 6000)
      .catch(() => { throw new Error("did not recover: " + JSON.stringify({ urls: revived.urls, infos: c.infos.slice(-4) })); });
    expect(revived.urls.at(-1)).toBe("/ws/runs/run-1?last_event_id=e1");
  }, 20_000);

  it("detects a silently dead link with the watchdog and reconnects", async () => {
    backend = new FakeBackend();
    await backend.start();
    backend.history.push(ev(1, "run.created"));
    const c = connect("run-1", { staleAfterMs: 250 });
    await until(() => c.get().events.length === 1);
    const connectionsBefore = backend.urls.length;
    backend.silent = true; // no heartbeats, no events: the link looks open but is dead
    await until(() => backend.urls.length > connectionsBefore, 15_000); // generous: real timers, machine may be loaded
    expect(c.states).toContain("reconnecting");
  }, 30_000);
});
