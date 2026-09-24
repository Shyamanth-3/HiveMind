import { describe, expect, it } from "vitest";
import { evt, snapshot, state, stateMsg } from "@/test-utils/fakeWebSocket";
import { initialStreamState, isTerminal, reduce, type StreamState } from "./reducer";
import type { ServerMessage } from "./types";

const apply = (s: StreamState, m: ServerMessage | object) => reduce(s, { type: "message", message: m as ServerMessage });
const types = (s: StreamState) => s.events.map((e) => e.event_type);

describe("telemetry reducer reliability", () => {
  it("A B B C -> A B C (duplicate delivery)", () => {
    const [a, b, c] = [evt("A"), evt("B"), evt("C")];
    let s = apply(initialStreamState, snapshot([a]));
    for (const e of [b, b, c]) s = apply(s, e);
    expect(types(s)).toEqual(["A", "B", "C"]);
  });

  it("out-of-order arrival is placed chronologically (A C B -> A B C)", () => {
    const [a, b, c] = [evt("A"), evt("B"), evt("C")];
    let s = apply(initialStreamState, snapshot([a]));
    s = apply(s, c);
    s = apply(s, b);
    expect(types(s)).toEqual(["A", "B", "C"]);
    expect(s.lastEventId).toBe(c.event_id); // resume cursor = newest event, not last arrival
  });

  it("a duplicate plus out-of-order burst converges to the same timeline as in-order delivery", () => {
    const evs = ["A", "B", "C", "D", "E"].map((t) => evt(t));
    const shuffled = [evs[3], evs[1], evs[1], evs[4], evs[0], evs[2], evs[3]];
    const s = shuffled.reduce((acc, e) => apply(acc, e), initialStreamState);
    expect(types(s)).toEqual(["A", "B", "C", "D", "E"]);
    expect(Object.keys(s.ids)).toHaveLength(5);
  });

  it("events with identical timestamps keep arrival order", () => {
    const t = "2026-09-24T10:00:00.000Z";
    const s = ["X", "Y", "Z"].reduce((acc, n) => apply(acc, evt(n, { timestamp: t })), initialStreamState);
    expect(types(s)).toEqual(["X", "Y", "Z"]);
  });

  it("reconnect: a resume snapshot after a drop adds only the missed events, once", () => {
    const [a, b, c, d] = [evt("A"), evt("B"), evt("C"), evt("D")];
    let s = apply(initialStreamState, snapshot([a, b]));
    s = apply(s, snapshot([b, c, d], { mode: "resume" }));   // overlap b must not duplicate
    s = apply(s, snapshot([c, d], { mode: "resume" }));      // second reconnect, nothing new
    expect(types(s)).toEqual(["A", "B", "C", "D"]);
  });

  it("a terminal state stays terminal even if late events or heartbeats arrive", () => {
    let s = apply(initialStreamState, snapshot([evt("run.created")]));
    s = apply(s, stateMsg(state({ status: "failed" })));
    expect(isTerminal(s)).toBe(true);
    s = apply(s, { type: "heartbeat" });
    s = apply(s, evt("strategy.created"));
    expect(isTerminal(s)).toBe(true);
  });

  it("malformed / unknown messages never throw and never change state", () => {
    const s = apply(initialStreamState, snapshot([evt("run.created")]));
    for (const junk of [{ type: "nope" }, { type: "workflow.event" }, { type: "pong" }]) {
      expect(() => apply(s, junk)).not.toThrow();
    }
    expect(types(apply(s, { type: "pong" }))).toEqual(["run.created"]);
  });
});
