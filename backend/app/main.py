from fastapi import FastAPI
from pydantic import BaseModel
from fastapi import HTTPException
from app.api.health import router as hr
app=FastAPI()

app.include_router(hr)

from app.core.config import settings

print(settings.DATABASE_URL)   