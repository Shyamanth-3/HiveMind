import asyncio
from uuid import uuid4

from agents.guardian.service import GuardianService
from agents.architect.schemas import ArchitecturePlan
from agents.scout.schemas import ResearchReport
from agents.builder.schemas import TaskGraph


async def main():
    # Construct mock inputs
    run_id = uuid4()
    goal = "Build a scalable multi-agent operating system for software development."
    
    mock_plan = ArchitecturePlan(
        workflow_run_id=run_id,
        goal=goal,
        summary="Architecture for an event-driven Multi-Agent OS.",
        components=[],
        dependencies=[],
        execution_order=[],
        milestones=[],
        risk_assessment=[]
    )
    
    mock_report = ResearchReport(
        workflow_run_id=run_id,
        goal=goal,
        summary="Research on Kafka and FastAPI integration.",
        findings=[],
        library_recommendations=[],
        security_considerations=[],
        performance_considerations=[]
    )
    
    mock_graph = TaskGraph(
        workflow_run_id=run_id,
        goal=goal,
        summary="Task graph for the OS implementation.",
        tasks=[
            {
                "id": 1,
                "title": "Set up API Gateway",
                "description": "Initialize FastAPI project.",
                "priority": "high",
                "dependencies": [],
                "estimated_complexity": "low",
                "required_files": ["main.py"],
                "acceptance_criteria": ["App starts"],
                "assigned_agent": "developer_agent"
            }
        ]
    )

    service = GuardianService()

    print(f"Running Guardian workflow for run {run_id}...")
    result = await service.generate_review(
        run_id=run_id,
        goal=goal,
        architecture_plan=mock_plan,
        research_report=mock_report,
        task_graph=mock_graph,
    )

    print("\n===== Guardian Validation Report =====")
    print(f"Run ID:  {result.workflow_run_id}")
    print(f"Summary: {result.summary}")
    print(f"Verdict: {result.overall_verdict.upper()}")
    
    print("\nArchitecture Review:")
    print(f"  Sound? {result.architecture_review.is_sound}")
    print(f"  Feedback: {result.architecture_review.feedback}")
    
    print("\nSecurity Review:")
    print(f"  Secure? {result.security_review.is_secure}")
    print(f"  Feedback: {result.security_review.feedback}")


if __name__ == "__main__":
    asyncio.run(main())
