import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key=os.getenv("GROQ_API_KEY")
model=os.getenv("LLM_MODEL")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1",
)

response=client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": "You are the Queen Agent."
        },
        {
            "role": "user",
            "content": "Introduce yourself."
        }
    ],
    temperature=0.2,
    max_tokens=100,
)
print("\n===== RESPONSE =====\n")
print(response.choices[0].message.content)
