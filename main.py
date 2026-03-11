from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from middleware.api_key import api_key_middleware

app = FastAPI()

# API Key middleware
@app.middleware("http")
async def api_key_middleware_wrapper(request: Request, call_next):
    return await api_key_middleware(request, call_next)

# CORS middleware (add after custom middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from api.ingest import router as ingest_router
from api.chat import router as chat_router
from api.list_user import router as user_router
from api.escalation import router as escalation_router

app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(user_router)
app.include_router(escalation_router)

@app.get("/health")
def health():
    return {"status": "ok"}