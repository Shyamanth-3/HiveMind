from agents.llm.base import BaseLLM
from agents.queen.prompts import SYSTEM_PROMPT


class QueenAgent:
    def __init__(self, llm: BaseLLM):
        self.llm = llm
    def generate_strategy(self, goal: str) -> str:
        user_prompt = f"""
Goal:

{goal}

Create a high-level execution strategy.
"""
        response = self.llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return response