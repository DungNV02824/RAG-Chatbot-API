from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Test: Import routers được không?
try:
    from api.ingest import router as ingest_router
    from api.chat import router as chat_router
    from api.list_user import router as user_router
    from api.escalation import router as escalation_router
    print("✓ Routers imported")
except Exception as e:
    print(f"✗ Router import error: {e}")
    ingest_router = chat_router = user_router = escalation_router = None

# Test: Models được không?
try:
    from models import user, conversation, message, document, order, escalation
    from db.base import Base, engine
    print("✓ Models imported")
except Exception as e:
    print(f"✗ Model import error: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if ingest_router:
    app.include_router(ingest_router)
if chat_router:
    app.include_router(chat_router)
if user_router:
    app.include_router(user_router)
if escalation_router:
    app.include_router(escalation_router)

@app.get("/health")
def health():
    return {"status": "ok"}