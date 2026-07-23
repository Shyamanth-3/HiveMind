import os

from dotenv import load_dotenv
from openai import OpenAI

from agents.llm.base import BaseLLM


class GroqLLM(BaseLLM):
    def __init__(self):
        self.client=OpenAI(
            api_key=os.getenv("Groq_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        self.model=os.getenv("LLM_MODEL")
    
    def generate(
        self,
        system_prompt:str,
        user_prompt:str,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                "role":"system",
                "content":system_prompt,
                },
                {
                "role":"user",
                "content":user_prompt,
                },
            ],
            temperature=0.2,
        )

        return response.choices[0].message.content