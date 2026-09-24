import { describe, expect, it } from "vitest";
import { evt } from "@/test-utils/fakeWebSocket";
import { buildRevisionTimeline, describeEvent } from "./view";

const review = (verdict: string, n: number) =>
  evt("review.completed", { revision_number: n, payload: { verdict, revision_number: n } });

describe("revision timeline", () => {
  it("is empty for a run approved on the first review", () => {
    const t = buildRevisionTimeline([evt("run.created"), review("approved", 0)]);
    expect(t).toEqual({ originalVerdict: "approved", revisions: [] });
  });

  it("tells the Guardian -> revision -> Builder -> Guardian story from events", () => {
    const t = buildRevisionTimeline([
      evt("tasks.generated", { revision_number: 0, payload: { task_count: 7, revision_number: 0 } }),
      review("needs_revision", 0),
      evt("revision.requested", {
        revision_number: 1,
        payload: { revision_number: 1, max_revisions: 3, reason: "Missing security", feedback: ["security: no auth", "performance: no index"], requested_changes: 6 },
      }),
      evt("tasks.generated", { revision_number: 1, payload: { task_count: 11, revision_number: 1 } }),
      review("approved", 1),
    ]);
    expect(t.originalVerdict).toBe("needs_revision");
    expect(t.revisions).toEqual([
      {
        revision: 1,
        reason: "Missing security",
        feedback: ["security: no auth", "performance: no index"],
        changeCount: 6,
        requestedAt: expect.any(String),
        taskCount: 11,
        outcome: "approved",
      },
    ]);
  });

  it("shows a revision in progress (no Builder output / verdict yet) as pending", () => {
    const t = buildRevisionTimeline([
      review("needs_revision", 0),
      evt("revision.requested", { revision_number: 1, payload: { revision_number: 1, feedback: [], requested_changes: 2 } }),
    ]);
    expect(t.revisions[0]).toMatchObject({ revision: 1, outcome: "pending" });
    expect(t.revisions[0].taskCount).toBeUndefined();
  });

  it("supports several revisions in order and records each outcome", () => {
    const req = (n: number) => evt("revision.requested", { revision_number: n, payload: { revision_number: n, feedback: ["x"], requested_changes: 1 } });
    const t = buildRevisionTimeline([review("needs_revision", 0), req(1), review("needs_revision", 1), req(2), review("approved", 2)]);
    expect(t.revisions.map((r) => [r.revision, r.outcome])).toEqual([[1, "needs_revision"], [2, "approved"]]);
  });

  it("ignores non-string feedback entries defensively", () => {
    const t = buildRevisionTimeline([
      evt("revision.requested", { revision_number: 1, payload: { revision_number: 1, feedback: ["ok", 5, null], requested_changes: "n/a" } }),
    ]);
    expect(t.revisions[0].feedback).toEqual(["ok"]);
    expect(t.revisions[0].changeCount).toBe(0);
  });
});

describe("describeEvent", () => {
  it("describes each event type from the backend summary only", () => {
    expect(describeEvent(evt("strategy.created", { payload: { phases: 5 } }))).toBe("Queen produced a strategy (5 phases)");
    expect(describeEvent(evt("tasks.generated", { payload: { task_count: 11, revision_number: 1 } }))).toBe("Builder produced revision 1 (11 tasks)");
    expect(describeEvent(review("needs_revision", 0))).toBe("Guardian: the plan needs revision");
    expect(describeEvent(review("approved", 2))).toBe("Guardian approved revision 2");
    expect(describeEvent(evt("revision.requested", { payload: { revision_number: 2 } }))).toBe("Revision 2 requested");
    expect(describeEvent(evt("run.failed", { payload: { error_type: "MAX_REVISIONS_EXCEEDED" } }))).toBe("Run failed (MAX_REVISIONS_EXCEEDED)");
    expect(describeEvent(evt("something.new"))).toBe("something.new");
  });
});
