from fastapi import FastAPI

from api.ingest import router as ingest_router
from api.chat import router as chat_router

app = FastAPI()

app.include_router(ingest_router)
app.include_router(chat_router)