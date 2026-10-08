import asyncio
from uuid import uuid4

from agents.builder.service import BuilderService
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport


async def main():
    # Construct mock inputs
    run_id = uuid4()
    goal = "Build a scalable multi-agent operating system for software development."
    
    mock_plan = ArchitecturePlan(
        workflow_run_id=run_id,
        goal=goal,
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
    
    mock_report = ResearchReport(
        workflow_run_id=run_id,
        goal=goal,
        summary="Research on Kafka and FastAPI integration.",
        findings=[
            {
                "topic": "Kafka Streaming",
                "finding": "confluent-kafka is recommended over aiokafka for throughput.",
                "source_type": "web",
                "relevance": "Directly impacts event bus component"
            }
        ],
        library_recommendations=[],
        security_considerations=[],
        performance_considerations=[]
    )

    service = BuilderService()

    print(f"Running Builder workflow for run {run_id}...")
    result = await service.generate_task_graph(
        run_id=run_id,
        goal=goal,
        architecture_plan=mock_plan,
        research_report=mock_report,
    )

    print("\n===== Builder Task Graph =====")
    print(f"Run ID:  {result.workflow_run_id}")
    print(f"Summary: {result.summary}")
    print(f"\nTasks ({len(result.tasks)}):")
    for t in result.tasks:
        print(f"  [{t.id}] {t.title} (Complexity: {t.estimated_complexity}, Priority: {t.priority})")
        print(f"        Agent: {t.assigned_agent}")
        print(f"        Depends on: {t.dependencies}")


if __name__ == "__main__":
    asyncio.run(main())
