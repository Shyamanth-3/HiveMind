import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agents, asWebSocket, evt, FakeWebSocket, snapshot, state, stateMsg } from "@/test-utils/fakeWebSocket";
import { useEventStream } from "./useEventStream";

const hook = (props: { runId: string | null; enabled?: boolean } = { runId: "run-1" }) =>
  renderHook((p: { runId: string | null; enabled?: boolean }) => useEventStream({ ...p, WebSocketImpl: asWebSocket }), {
    initialProps: props,
  });

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.reset();
});
afterEach(() => vi.useRealTimers());

describe("useEventStream", () => {
  it("goes connecting -> connected and applies the snapshot then live events", () => {
    const { result } = hook();
    expect(result.current.connectionState).toBe("connecting");
    act(() => FakeWebSocket.last.open());
    expect(result.current.connectionState).toBe("connected");
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created")])));
    act(() => FakeWebSocket.last.message(evt("strategy.created", { payload: { phases: 5 } })));
    act(() =>
      FakeWebSocket.last.message(
        stateMsg(state({ agents: agents({ queen: { status: "completed" }, architect: { status: "running" } }) })),
      ),
    );
    expect(result.current.events.map((e) => e.event_type)).toEqual(["run.created", "strategy.created"]);
    expect(result.current.state?.agents.architect.status).toBe("running");
    expect(result.current.lastEvent?.event_type).toBe("strategy.created");
    expect(result.current.isTerminal).toBe(false);
  });

  it("uses the real telemetry URL for the run", () => {
    hook({ runId: "run-1" });
    expect(FakeWebSocket.last.url).toBe("ws://localhost:8000/ws/runs/run-1");
  });

  it("a dropped connection is 'reconnecting', keeps the events, and resumes after the last one", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    const [a, b] = [evt("run.created"), evt("strategy.created")];
    act(() => FakeWebSocket.last.message(snapshot([a, b])));
    act(() => FakeWebSocket.last.serverClose(1006));
    expect(result.current.connectionState).toBe("reconnecting");
    expect(result.current.events).toHaveLength(2); // nothing is thrown away
    expect(result.current.state?.status).toBe("running"); // and the workflow is NOT shown as failed
    expect(result.current.nextRetryMs).toBeGreaterThan(0);

    act(() => void vi.advanceTimersByTime(1500));
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.last.url).toBe(`ws://localhost:8000/ws/runs/run-1?last_event_id=${b.event_id}`);
  });

  it("recovered events are appended once: overlapping / re-delivered events are deduplicated", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    const [a, b, c, d] = [evt("run.created"), evt("strategy.created"), evt("architecture.created"), evt("research.completed")];
    act(() => FakeWebSocket.last.message(snapshot([a, b])));
    act(() => FakeWebSocket.last.serverClose(1006));
    act(() => void vi.advanceTimersByTime(1500));
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.message(snapshot([b, c, d], { mode: "resume" }))); // server overlaps b
    act(() => FakeWebSocket.last.message(d)); // a live duplicate of d
    expect(result.current.events.map((e) => e.event_id)).toEqual([a, b, c, d].map((e) => e.event_id));
    expect(result.current.connectionState).toBe("connected");
  });

  it("run.completed marks the workflow terminal but the connection stays connected", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created")])));
    act(() => FakeWebSocket.last.message(evt("run.completed")));
    act(() => FakeWebSocket.last.message(stateMsg(state({ status: "completed", is_completed: true }))));
    expect(result.current.isTerminal).toBe(true);
    expect(result.current.connectionState).toBe("connected");
  });

  it("does not reconnect after the run finished, and reports disconnected (not failed)", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created"), evt("run.completed")], { state: state({ status: "completed" }) })));
    act(() => FakeWebSocket.last.serverClose(1006));
    expect(result.current.connectionState).toBe("disconnected");
    act(() => void vi.advanceTimersByTime(120_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(result.current.state?.status).toBe("completed");
  });

  it("run.failed shows a failed workflow with a safe summary; the socket state is separate", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    const failure = { failed_stage: "scout", error_type: "RuntimeError", message: "boom" };
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created")])));
    act(() => FakeWebSocket.last.message(evt("run.failed", { payload: failure })));
    act(() => FakeWebSocket.last.message(stateMsg(state({ status: "failed", failure }))));
    expect(result.current.state?.status).toBe("failed");
    expect(result.current.state?.failure?.message).toBe("boom");
    expect(result.current.isTerminal).toBe(true);
    expect(result.current.connectionState).toBe("connected");
  });

  it("an unknown run (4404) is an error state with a reason, and reconnect() retries", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.serverClose(4404));
    expect(result.current.connectionState).toBe("error");
    expect(result.current.error).toBe("run not found");
    act(() => result.current.reconnect());
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(result.current.connectionState).toBe("connecting");
  });

  it("switching runs resets the stream and connects to the new run", () => {
    const { result, rerender } = hook({ runId: "run-1" });
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created")])));
    expect(result.current.events).toHaveLength(1);
    rerender({ runId: "run-2" });
    expect(result.current.events).toHaveLength(0);
    expect(FakeWebSocket.last.url).toBe("ws://localhost:8000/ws/runs/run-2");
    expect(FakeWebSocket.instances[0].closedByClient?.code).toBe(1000);
  });

  it("enabled=false or no runId opens nothing; unmount closes the socket", () => {
    const off = hook({ runId: "run-1", enabled: false });
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(off.result.current.connectionState).toBe("disconnected");
    hook({ runId: null });
    expect(FakeWebSocket.instances).toHaveLength(0);
    const live = hook({ runId: "run-1" });
    const sock = FakeWebSocket.last;
    live.unmount();
    expect(sock.closedByClient?.code).toBe(1000);
  });

  it("the browser coming back online reconnects immediately instead of waiting for the backoff", () => {
    const { result } = hook();
    act(() => FakeWebSocket.last.open());
    act(() => FakeWebSocket.last.message(snapshot([evt("run.created")])));
    act(() => FakeWebSocket.last.serverClose(1006));
    expect(result.current.connectionState).toBe("reconnecting");
    act(() => void window.dispatchEvent(new Event("online")));
    expect(FakeWebSocket.instances).toHaveLength(2);
  });
});
