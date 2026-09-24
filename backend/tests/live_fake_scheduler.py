"""
DEV TOOL (not a test): run the REAL scheduler process (real Kafka consumer, real PostgreSQL, real notifications)
with deterministic fake agents, so the real-time UI can be exercised without spending LLM credits.

    python -m tests.live_fake_scheduler          # from backend/, needs docker compose Postgres + Kafka

Behaviour is driven by the goal text of each run:
    "revise"  -> Guardian returns needs_revision for the original plan, then approves revision 1
    "fail"    -> Scout raises (run.failed)
    "always"  -> Guardian never approves (hits MAX_REVISIONS)
FAKE_DELAY_S (default 2.0) is how long each fake agent "works".
"""

import os

from tests import fakes
from tests.fakes import (
    FakeArchitect, FakeBuilder, FakeGuardian, FakeQueen, FakeScout, VERDICT,
)

DELAY_S = float(os.environ.get("FAKE_DELAY_S", "2.0"))
fakes.reset_fakes()
fakes.DELAY[0] = DELAY_S


class GoalAwareScout(FakeScout):
    async def generate_research(self, run_id, goal, plan):
        if "fail" in goal.lower():
            fakes.CALLS.append("scout")
            import time
            time.sleep(DELAY_S)
            raise RuntimeError("Scout could not reach its data source (simulated failure)")
        return await super().generate_research(run_id, goal, plan)


class GoalAwareGuardian(FakeGuardian):
    async def generate_review(self, run_id, goal, plan, report, graph, revision_number=0, previous_requested_changes=None):
        g = goal.lower()
        VERDICT[:] = ["needs_revision"] if ("always" in g or ("revise" in g and revision_number == 0)) else ["approved"]
        return await super().generate_review(run_id, goal, plan, report, graph, revision_number, previous_requested_changes)


def main() -> None:
    from app.scheduler import consumer
    consumer.QueenService = FakeQueen
    consumer.ArchitectService = FakeArchitect
    consumer.ScoutService = GoalAwareScout
    consumer.BuilderService = FakeBuilder
    consumer.GuardianService = GoalAwareGuardian
    from app.scheduler.__main__ import main as scheduler_main
    scheduler_main()


if __name__ == "__main__":
    main()
