from pydantic import BaseModel

class StratergyPhase(BaseModel):
    id:int
    title:str
    description:str

class Stratergy(BaseModel):
    goal: str
    summary: str
    phases: list[StratergyPhase]