import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from agents.llm.base import BaseLLM
from agents.llm.groq_client import GroqLLM

load_dotenv()

def get_llm() -> BaseLLM:
    provider = os.getenv("LLM_PROVIDER")

    if provider == "groq":
        return GroqLLM()
    
    raise ValueError(f"Unsupported LLM proivder: {provider}")
    