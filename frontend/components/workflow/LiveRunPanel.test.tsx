import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agents, evt, FakeWebSocket, snapshot, state, stateMsg } from "@/test-utils/fakeWebSocket";
import { LiveRunPanel } from "./LiveRunPanel";

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.reset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const send = (m: object) => act(() => void FakeWebSocket.last.message(m as Record<string, unknown>));
const status = (id: string) => screen.getByTestId(`agent-${id}`).getAttribute("data-status");
const rows = () => screen.queryAllByTestId("event-row").map((r) => r.getAttribute("data-event-type"));

function open() {
  render(<LiveRunPanel runId="run-1" />);
  act(() => void FakeWebSocket.last.open());
}

describe("LiveRunPanel", () => {
  it("shows connecting, then Live, and the five agents pending", () => {
    render(<LiveRunPanel runId="run-1" />);
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("connecting");
    act(() => void FakeWebSocket.last.open());
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("connected");
    expect(["queen", "architect", "scout", "builder", "guardian"].map(status)).toEqual(Array(5).fill("pending"));
  });

  it("agent cards follow real backend state, not timers", () => {
    open();
    send(snapshot([evt("run.created"), evt("strategy.created"), evt("architecture.created")], {
      state: state({ agents: agents({ queen: { status: "completed" }, architect: { status: "completed" }, scout: { status: "running" } }) }),
    }));
    expect(["queen", "architect", "scout", "builder", "guardian"].map(status)).toEqual(
      ["completed", "completed", "running", "pending", "pending"],
    );
    vi.advanceTimersByTime(60_000); // time passing changes nothing
    expect(status("scout")).toBe("running");
    send(stateMsg(state({ agents: agents({ queen: { status: "completed" }, architect: { status: "completed" }, scout: { status: "completed" }, builder: { status: "running" } }) })));
    expect(status("scout")).toBe("completed");
    expect(status("builder")).toBe("running");
  });

  it("renders the event log from events, newest first, without duplicates", () => {
    open();
    const created = evt("run.created", { payload: { goal: "Build a bakery site" } });
    send(snapshot([created]));
    const strat = evt("strategy.created", { payload: { phases: 4 } });
    send(strat);
    send(strat); // re-delivered
    send({ ...strat });
    expect(rows()).toEqual(["strategy.created", "run.created"]);
    expect(screen.getByText("Build a bakery site")).toBeTruthy();
    expect(screen.getByText("Queen produced a strategy (4 phases)")).toBeTruthy();
  });

  it("visualises a revision: needs revision -> revision N -> Builder -> approved", () => {
    open();
    send(snapshot([
      evt("tasks.generated", { revision_number: 0, payload: { task_count: 7, revision_number: 0 } }),
      evt("review.completed", { revision_number: 0, payload: { verdict: "needs_revision", revision_number: 0 } }),
      evt("revision.requested", {
        revision_number: 1,
        payload: { revision_number: 1, max_revisions: 3, reason: "r", feedback: ["security: no auth"], requested_changes: 6 },
      }),
    ], { state: state({ revision: { count: 1, max: 3, current: 1, status: "requested" }, agents: agents({ builder: { status: "running", revision: 1 }, guardian: { status: "pending", revision: 1 } }) }) }));
    let tl = screen.getByTestId("revision-timeline");
    expect(within(tl).getByTestId("revision-original").textContent).toContain("needs revision");
    expect(within(tl).getByTestId("revision-1").textContent).toContain("Revision 1 of 3 requested");
    expect(within(tl).getByTestId("revision-1").textContent).toContain("1 feedback · 6 requested changes");
    expect(within(tl).getByText("• security: no auth")).toBeTruthy();
    expect(screen.getByTestId("revision-1").getAttribute("data-outcome")).toBe("pending");
    expect(screen.getByTestId("agent-builder").textContent).toContain("rev 1");

    send(evt("tasks.generated", { revision_number: 1, payload: { task_count: 11, revision_number: 1 } }));
    send(evt("review.completed", { revision_number: 1, payload: { verdict: "approved", revision_number: 1 } }));
    tl = screen.getByTestId("revision-timeline");
    expect(screen.getByTestId("revision-1").getAttribute("data-outcome")).toBe("approved");
    expect(tl.textContent).toContain("Builder produced 11 tasks");
    expect(tl.textContent).toContain("Guardian approved");
  });

  it("run.completed shows a completed banner while the connection stays Live", () => {
    open();
    send(snapshot([evt("run.created")]));
    send(evt("run.completed", { payload: { revision_count: 1 } }));
    send(stateMsg(state({ status: "completed", is_completed: true, revision: { count: 1, max: 3, current: 1, status: "approved" }, agents: agents({ queen: { status: "completed" }, guardian: { status: "completed" } }) })));
    expect(screen.getByTestId("terminal-completed").textContent).toContain("Run completed after 1 revision");
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("connected");
    expect(screen.queryByTestId("terminal-failed")).toBeNull();
  });

  it("run.failed shows a safe summary (stage, type, message) and no internals", () => {
    open();
    const failure = { failed_stage: "guardian", error_type: "MAX_REVISIONS_EXCEEDED", message: "Guardian still asked for changes after 3 revision(s)" };
    send(snapshot([evt("run.created")]));
    send(evt("run.failed", { payload: failure }));
    send(stateMsg(state({ status: "failed", failure, agents: agents({ guardian: { status: "failed", error_type: "MAX_REVISIONS_EXCEEDED" } }) })));
    const banner = screen.getByTestId("terminal-failed");
    expect(banner.textContent).toContain("Run failed at guardian — MAX_REVISIONS_EXCEEDED");
    expect(banner.textContent).toContain("Guardian still asked for changes");
    expect(status("guardian")).toBe("failed");
    expect(banner.textContent).not.toMatch(/Traceback|stack|sk-/);
  });

  it("a dropped connection never looks like a failed workflow", () => {
    open();
    send(snapshot([evt("run.created"), evt("strategy.created")], { state: state({ agents: agents({ queen: { status: "completed" }, architect: { status: "running" } }) }) }));
    act(() => void FakeWebSocket.last.serverClose(1006));
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("reconnecting");
    expect(screen.queryByTestId("terminal-failed")).toBeNull();
    expect(status("architect")).toBe("running"); // last known state stays on screen
    expect(screen.getByTestId("paused-note").textContent).toContain("The run keeps going on the server");
    expect(rows()).toEqual(["strategy.created", "run.created"]);
  });

  it("recovers after reconnect: missed events appear once, in order", () => {
    open();
    const [a, b, c, d] = [evt("run.created"), evt("strategy.created"), evt("architecture.created"), evt("research.completed")];
    send(snapshot([a, b]));
    act(() => void FakeWebSocket.last.serverClose(1006));
    act(() => void vi.advanceTimersByTime(1500));
    expect(FakeWebSocket.last.url).toContain(`last_event_id=${b.event_id}`);
    act(() => void FakeWebSocket.last.open());
    send(snapshot([c, d], { mode: "resume" }));
    expect(rows()).toEqual(["research.completed", "architecture.created", "strategy.created", "run.created"]);
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("connected");
    expect(screen.queryByTestId("paused-note")).toBeNull();
  });

  it("a page refresh (remount) rebuilds the same view from a full snapshot, with no duplicates", () => {
    const history = [evt("run.created"), evt("strategy.created"), evt("architecture.created")];
    const first = render(<LiveRunPanel runId="run-1" />);
    act(() => void FakeWebSocket.last.open());
    send(snapshot(history));
    const before = rows();
    first.unmount(); // browser refresh: all client state is gone
    render(<LiveRunPanel runId="run-1" />);
    expect(FakeWebSocket.last.url).toBe("ws://localhost:8000/ws/runs/run-1"); // no cursor: it starts from scratch
    act(() => void FakeWebSocket.last.open());
    send(snapshot(history, { mode: "full" }));
    expect(rows()).toEqual(before);
  });

  it("an unknown run shows a connection error with a Reconnect button, not a workflow failure", () => {
    open();
    act(() => void FakeWebSocket.last.serverClose(4404));
    expect(screen.getByTestId("connection-badge").getAttribute("data-state")).toBe("error");
    expect(screen.getByText("Reconnect")).toBeTruthy();
    expect(screen.queryByTestId("terminal-failed")).toBeNull();
  });
});
