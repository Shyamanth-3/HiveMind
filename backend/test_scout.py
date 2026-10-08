import asyncio
from uuid import uuid4

from agents.scout.service import ScoutService
from agents.architect.schemas import ArchitecturePlan


async def main():
    # Construct a mock architecture plan
    mock_plan = ArchitecturePlan(
        workflow_run_id=uuid4(),
        goal="Build a scalable multi-agent operating system for software development.",
        summary="Architecture for an event-driven Multi-Agent OS.",
        components=[
            {
                "id": "api_gateway",
                "name": "API Gateway",
                "description": "FastAPI entry point for the system",
                "layer": "backend"
            },
            {
                "id": "event_bus",
                "name": "Kafka Event Bus",
                "description": "Handles async event streaming",
                "layer": "infrastructure"
            }
        ],
        dependencies=[],
        execution_order=["event_bus", "api_gateway"],
        milestones=[],
        risk_assessment=[]
    )

    service = ScoutService()

    print(f"Running Scout workflow for run {mock_plan.workflow_run_id}...")
    result = await service.generate_research(
        run_id=mock_plan.workflow_run_id,
        goal=mock_plan.goal,
        architecture_plan=mock_plan,
    )

    print("\n===== Scout Research Report =====")
    print(f"Run ID:  {result.workflow_run_id}")
    print(f"Summary: {result.summary}")
    print(f"\nFindings ({len(result.findings)}):")
    for f in result.findings:
        print(f"  [{f.topic}] {f.finding} (Source: {f.source_type})")
        
    print(f"\nLibraries ({len(result.library_recommendations)}):")
    for lib in result.library_recommendations:
        print(f"  {lib.name}: {lib.purpose} -> {lib.rationale}")
        
    print(f"\nSecurity ({len(result.security_considerations)}):")
    for sec in result.security_considerations:
        print(f"  [{sec.severity.upper()}] {sec.area}: {sec.concern} -> {sec.recommendation}")


if __name__ == "__main__":
    asyncio.run(main())
