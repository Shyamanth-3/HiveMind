import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { asWebSocket, FakeWebSocket, snapshot } from "@/test-utils/fakeWebSocket";
import { TelemetryClient, type ConnectionInfo } from "./client";
import type { ConnectionState, ServerMessage } from "./types";

function setup(over: Partial<ConstructorParameters<typeof TelemetryClient>[0]> = {}) {
  const states: { s: ConnectionState; info?: ConnectionInfo }[] = [];
  const messages: ServerMessage[] = [];
  let last: string | null = null;
  const client = new TelemetryClient({
    url: (l) => `ws://x/ws/runs/run-1${l ? `?last_event_id=${l}` : ""}`,
    getLastEventId: () => last,
    onMessage: (m) => messages.push(m),
    onConnectionState: (s, info) => states.push({ s, info }),
    WebSocketImpl: asWebSocket,
    random: () => 0.5, // jitter factor exactly 1.0
    ...over,
  });
  return { client, states, messages, setLast: (v: string | null) => (last = v), names: () => states.map((x) => x.s) };
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.reset();
});
afterEach(() => vi.useRealTimers());

describe("TelemetryClient connection states", () => {
  it("connecting -> connected on open", () => {
    const t = setup();
    t.client.start();
    expect(t.names()).toEqual(["connecting"]);
    FakeWebSocket.last.open();
    expect(t.names()).toEqual(["connecting", "connected"]);
  });

  it("a dropped socket is 'reconnecting' (never a failure) and reconnects after the backoff", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.open();
    FakeWebSocket.last.message(snapshot([]));
    FakeWebSocket.last.serverClose(1006);
    expect(t.names().at(-1)).toBe("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(999);
    expect(FakeWebSocket.instances).toHaveLength(1); // still waiting: no tight loop
    vi.advanceTimersByTime(2);
    expect(FakeWebSocket.instances).toHaveLength(2);
    FakeWebSocket.last.open();
    expect(t.names().at(-1)).toBe("connected");
  });

  it("stop() closes the socket, cancels retries and reports disconnected", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.open();
    t.client.stop();
    expect(t.names().at(-1)).toBe("disconnected");
    expect(FakeWebSocket.last.closedByClient?.code).toBe(1000);
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

describe("backoff", () => {
  it("doubles with each failed attempt, is capped, and jitter stays within bounds", () => {
    const d = (n: number, r: number) => TelemetryClient.delayFor(n, 1000, 30_000, 0.25, () => r);
    expect([1, 2, 3, 4, 5, 6].map((n) => d(n, 0.5))).toEqual([1000, 2000, 4000, 8000, 16000, 30000]);
    expect(d(20, 0.5)).toBe(30_000); // capped
    expect(d(3, 0)).toBe(3000); // -25%
    expect(d(3, 1)).toBe(5000); // +25%
  });

  it("consecutive failures back off 1s, 2s, 4s (no reconnect storm)", () => {
    const t = setup();
    t.client.start();
    const delays: number[] = [];
    for (let i = 0; i < 3; i++) {
      FakeWebSocket.last.serverClose(1006); // never got a snapshot: attempt count keeps growing
      delays.push(t.states.at(-1)!.info!.nextRetryMs!);
      vi.advanceTimersByTime(delays[i] + 1);
    }
    expect(delays).toEqual([1000, 2000, 4000]);
  });

  it("resets the backoff once a snapshot proves a full round trip", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.serverClose(1006);
    vi.advanceTimersByTime(1001);
    FakeWebSocket.last.serverClose(1006);
    vi.advanceTimersByTime(2001);
    FakeWebSocket.last.open();
    FakeWebSocket.last.message(snapshot([]));
    FakeWebSocket.last.serverClose(1006);
    expect(t.states.at(-1)!.info!.nextRetryMs).toBe(1000); // back to the base delay
  });
});

describe("resume after reconnect", () => {
  it("reconnects with ?last_event_id= of the last applied event", () => {
    const t = setup();
    t.client.start();
    expect(FakeWebSocket.last.url).toBe("ws://x/ws/runs/run-1");
    FakeWebSocket.last.open();
    t.setLast("evt-42");
    FakeWebSocket.last.serverClose(1006);
    vi.advanceTimersByTime(1001);
    expect(FakeWebSocket.last.url).toBe("ws://x/ws/runs/run-1?last_event_id=evt-42");
  });

  it("a manual reconnect() skips the backoff and connects now", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.serverClose(1006);
    expect(t.names().at(-1)).toBe("reconnecting");
    t.client.reconnect();
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(t.names().at(-1)).toBe("connecting");
  });
});

describe("non-retryable and terminal cases", () => {
  it.each([[4404, "run not found"], [4400, "invalid run id"], [1008, "connection rejected (origin not allowed)"]])(
    "close code %i is an error and is never retried",
    (code, reason) => {
      const t = setup();
      t.client.start();
      FakeWebSocket.last.open();
      FakeWebSocket.last.serverClose(code);
      expect(t.states.at(-1)).toMatchObject({ s: "error", info: { error: reason } });
      vi.advanceTimersByTime(120_000);
      expect(FakeWebSocket.instances).toHaveLength(1);
    },
  );

  it("does not reconnect once the workflow is finished (shouldReconnect=false)", () => {
    let done = false;
    const t = setup({ shouldReconnect: () => !done });
    t.client.start();
    FakeWebSocket.last.open();
    done = true;
    FakeWebSocket.last.serverClose(1006);
    expect(t.names().at(-1)).toBe("disconnected");
    vi.advanceTimersByTime(120_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("1013 (slow consumer) is retried, it is not an error", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.open();
    FakeWebSocket.last.serverClose(1013);
    expect(t.names().at(-1)).toBe("reconnecting");
  });
});

describe("liveness watchdog", () => {
  it("reconnects when nothing (not even a heartbeat) arrives for staleAfterMs", () => {
    const t = setup({ staleAfterMs: 50_000 });
    t.client.start();
    FakeWebSocket.last.open();
    FakeWebSocket.last.message(snapshot([]));
    vi.advanceTimersByTime(49_000);
    FakeWebSocket.last.message({ type: "heartbeat", ts: "x" }); // re-arms the watchdog
    vi.advanceTimersByTime(49_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(2_000); // 51s of silence
    expect(FakeWebSocket.instances[0].closedByClient?.code).toBe(4000);
    expect(t.names().at(-1)).toBe("reconnecting");
  });
});

describe("robustness", () => {
  it("ignores malformed frames and keeps working", () => {
    const t = setup();
    t.client.start();
    FakeWebSocket.last.open();
    FakeWebSocket.last.raw("not json {");
    FakeWebSocket.last.message({ type: "heartbeat", ts: "x" });
    expect(t.messages).toEqual([{ type: "heartbeat", ts: "x" }]);
  });

  it("a stale (replaced) socket cannot drive the state machine", () => {
    const t = setup();
    t.client.start();
    const first = FakeWebSocket.last;
    t.client.reconnect();
    const before = t.names().length;
    first.serverClose(1006);
    first.message({ type: "heartbeat", ts: "late" });
    expect(t.names().length).toBe(before);
    expect(t.messages).toEqual([]);
  });

  it("start() twice does not open two sockets", () => {
    const t = setup();
    t.client.start();
    t.client.start();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
