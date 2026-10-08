import asyncio
from uuid import uuid4

from agents.architect.service import ArchitectService
from agents.queen.schemas import Strategy


async def main():
    # Construct a mock strategy that Queen would normally output
    mock_strategy = Strategy(
        workflow_run_id=uuid4(),
        goal="Build a scalable multi-agent operating system for software development.",
        summary="This project aims to build an event-driven multi-agent OS.",
        phases=[
            {"id": 1, "title": "Foundation", "description": "Set up FastAPI and Kafka."},
            {"id": 2, "title": "Agents", "description": "Implement Queen and Architect agents."},
        ]
    )

    service = ArchitectService()

    print(f"Running Architect workflow for run {mock_strategy.workflow_run_id}...")
    result = await service.generate_plan(
        run_id=mock_strategy.workflow_run_id,
        goal=mock_strategy.goal,
        strategy=mock_strategy,
    )

    print("\n===== Architect Plan =====")
    print(f"Run ID:  {result.workflow_run_id}")
    print(f"Goal:    {result.goal}")
    print(f"Summary: {result.summary}")
    print(f"\nComponents ({len(result.components)}):")
    for comp in result.components:
        print(f"  [{comp.id}] {comp.name} ({comp.layer}) - {comp.description}")
        
    print(f"\nDependencies ({len(result.dependencies)}):")
    for dep in result.dependencies:
        print(f"  {dep.source_id} -> {dep.target_id} ({dep.relationship})")
        
    print(f"\nMilestones ({len(result.milestones)}):")
    for ms in result.milestones:
        print(f"  [{ms.id}] {ms.title}: {ms.components}")


if __name__ == "__main__":
    asyncio.run(main())
