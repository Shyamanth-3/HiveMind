import asyncio
from uuid import uuid4

from agents.queen.service import QueenService
from agents.architect.service import ArchitectService
from agents.scout.service import ScoutService
from agents.builder.service import BuilderService
from agents.guardian.service import GuardianService


async def run_pipeline():
    run_id = uuid4()
    goal = "Build a scalable multi-agent operating system for software development."
    print(f"\n==========================================")
    print(f"STARTING END-TO-END PIPELINE")
    print(f"Run ID: {run_id}")
    print(f"Goal:   {goal}")
    print(f"==========================================\n")

    # 1. Queen (Goal -> Strategy)
    print(f"Dispatching Queen Agent...")
    queen_svc = QueenService()
    strategy = await queen_svc.generate_strategy(run_id, goal)
    print(f"   [SUCCESS] Strategy generated: {len(strategy.phases)} phases.\n")

    # 2. Architect (Strategy -> Architecture Plan)
    print(f"Dispatching Architect Agent...")
    architect_svc = ArchitectService()
    plan = await architect_svc.generate_plan(run_id, goal, strategy)
    print(f"   [SUCCESS] Architecture Plan generated: {len(plan.components)} components, {len(plan.dependencies)} dependencies.\n")

    # 3. Scout (Architecture Plan -> Research Report)
    print(f"Dispatching Scout Agent...")
    scout_svc = ScoutService()
    report = await scout_svc.generate_research(run_id, goal, plan)
    print(f"   [SUCCESS] Research Report generated: {len(report.findings)} findings.\n")

    # 4. Builder (Architecture Plan + Research Report -> Task Graph)
    print(f"Dispatching Builder Agent...")
    builder_svc = BuilderService()
    graph = await builder_svc.generate_task_graph(run_id, goal, plan, report)
    print(f"   [SUCCESS] Task Graph generated: {len(graph.tasks)} tasks.\n")

    # 5. Guardian (All Inputs -> Validation Report)
    print(f"Dispatching Guardian Agent...")
    guardian_svc = GuardianService()
    review = await guardian_svc.generate_review(run_id, goal, plan, report, graph)
    print(f"   [SUCCESS] Validation Report generated: {review.overall_verdict.upper()}.\n")

    print(f"==========================================")
    print(f"PIPELINE EXECUTION COMPLETE")
    print(f"==========================================")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
