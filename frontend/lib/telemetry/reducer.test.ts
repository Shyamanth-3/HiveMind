import { describe, expect, it } from "vitest";
import { evt, snapshot, state, stateMsg } from "@/test-utils/fakeWebSocket";
import { initialStreamState, isTerminal, reduce, type StreamState } from "./reducer";
import type { ServerMessage } from "./types";

const apply = (s: StreamState, m: ServerMessage | object) => reduce(s, { type: "message", message: m as ServerMessage });

describe("reducer", () => {
  it("a full snapshot establishes events, state and the resume cursor", () => {
    const a = evt("run.created"), b = evt("strategy.created");
    const s = apply(initialStreamState, snapshot([a, b], { state: state({ current_stage: "architecture.created" }) }));
    expect(s.events.map((e) => e.event_type)).toEqual(["run.created", "strategy.created"]);
    expect(s.lastEventId).toBe(b.event_id);
    expect(s.synced).toBe(true);
    expect(s.state?.current_stage).toBe("architecture.created");
  });

  it("applies live events in order", () => {
    let s = apply(initialStreamState, snapshot([evt("run.created")]));
    s = apply(s, evt("strategy.created"));
    s = apply(s, evt("architecture.created"));
    expect(s.events.map((e) => e.event_type)).toEqual(["run.created", "strategy.created", "architecture.created"]);
    expect(s.lastEventId).toBe(s.events[2].event_id);
  });

  it("deduplicates by event_id: a re-delivered event changes nothing", () => {
    const a = evt("run.created");
    let s = apply(initialStreamState, snapshot([a]));
    const before = s;
    s = apply(s, a);
    s = apply(s, { ...a }); // same id, different object
    expect(s).toBe(before); // same reference: no state change at all
    expect(s.events).toHaveLength(1);
  });

  it("a resume snapshot appends only what was missed and never duplicates", () => {
    const [a, b, c, d] = [evt("run.created"), evt("strategy.created"), evt("architecture.created"), evt("research.completed")];
    let s = apply(initialStreamState, snapshot([a, b]));
    s = apply(s, snapshot([b, c, d], { mode: "resume" })); // server overlaps b: still deduplicated
    expect(s.events.map((e) => e.event_id)).toEqual([a.event_id, b.event_id, c.event_id, d.event_id]);
    expect(s.lastEventId).toBe(d.event_id);
  });

  it("a full snapshot replaces history (page refresh / unknown cursor)", () => {
    let s = apply(initialStreamState, snapshot([evt("run.created"), evt("strategy.created")]));
    const fresh = [evt("run.created", { event_id: "new-1" })];
    s = apply(s, snapshot(fresh, { mode: "full" }));
    expect(s.events.map((e) => e.event_id)).toEqual(["new-1"]);
  });

  it("workflow.state replaces the authoritative state; heartbeats and pongs change nothing", () => {
    let s = apply(initialStreamState, snapshot([evt("run.created")]));
    const before = s;
    expect(apply(s, { type: "heartbeat", ts: "x" })).toBe(before);
    expect(apply(s, { type: "pong" })).toBe(before);
    s = apply(s, stateMsg(state({ status: "completed", is_completed: true })));
    expect(s.state?.status).toBe("completed");
  });

  it("ignores a state message for a different run", () => {
    const s = apply(initialStreamState, snapshot([evt("run.created")]));
    expect(apply(s, stateMsg(state({ run_id: "other-run", status: "failed" }))).state?.status).toBe("running");
  });

  it("reset returns to the initial state", () => {
    const s = apply(initialStreamState, snapshot([evt("run.created")]));
    expect(reduce(s, { type: "reset" })).toEqual(initialStreamState);
  });

  it("isTerminal reflects the WORKFLOW (state or terminal event), not the socket", () => {
    expect(isTerminal(initialStreamState)).toBe(false);
    expect(isTerminal(apply(initialStreamState, snapshot([evt("run.created")])))).toBe(false);
    expect(isTerminal(apply(initialStreamState, snapshot([], { state: state({ status: "completed" }) })))).toBe(true);
    expect(isTerminal(apply(initialStreamState, snapshot([evt("run.failed")])))).toBe(true);
    expect(isTerminal(apply(apply(initialStreamState, snapshot([evt("run.created")])), evt("run.completed")))).toBe(true);
  });
});
