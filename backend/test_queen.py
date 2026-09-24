import asyncio
from uuid import uuid4

from agents.llm.factory import get_llm
from agents.queen.workflow import QueenWorkflow


async def main():
    workflow = QueenWorkflow(
        llm=get_llm(),
    )

    result = await workflow.run(
        workflow_run_id=uuid4(),
        goal="Build a scalable multi-agent operating system for software development.",
    )

    print("\n===== Queen Strategy =====")
    print(f"Run ID:  {result.workflow_run_id}")
    print(f"Goal:    {result.goal}")
    print(f"Summary: {result.summary}")
    print(f"\nPhases ({len(result.phases)}):")
    for phase in result.phases:
        print(f"  [{phase.id}] {phase.title}")
        print(f"       {phase.description}")


if __name__ == "__main__":
    asyncio.run(main())