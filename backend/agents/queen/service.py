from agents.llm.factory import get_llm
from agents.queen.agent import QueenAgent

class QueenService:
    def __init__(self):
        llm=get_llm()
        self.agent=QueenAgent(llm)
    def generate_strategy(self,goal:str)->str:
        return self.agent.generate_strategy(goal)