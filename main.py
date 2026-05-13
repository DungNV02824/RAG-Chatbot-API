from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from middleware.api_key import api_key_middleware
from api.data_upload import router as ingest_router
from api.chat import router as chat_router
from api.user import router as user_router
from api.escalation import router as escalation_router
from api.tenant import router as tenant_router
from api.staff import router as staff_router
from api.payment import router as payment_router


# ========== STARTUP & SHUTDOWN EVENTS ==========
async def init_services():
    """Initialize background services on startup"""
    try:
        from core.queue import init_queue
        await init_queue()
        print("✓ Async task queue initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize task queue: {e}")
    
    try:
        from core.cache import redis_client
        redis_client.ping()
        print("✓ Redis cache connected")
    except Exception as e:
        print(f"⚠️ Failed to connect to Redis: {e}")


async def shutdown_services():
    """Cleanup on shutdown"""
    try:
        from core.queue import close_queue
        await close_queue()
        print("✓ Async task queue closed")
    except Exception as e:
        print(f"⚠️ Error closing task queue: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    # Startup
    await init_services()
    yield
    # Shutdown
    await shutdown_services()


# ========== CREATE APP ==========
app = FastAPI(lifespan=lifespan)

# 1. CORS Middleware phải nằm trên cùng
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5175", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "x-api-key"], 
    expose_headers=["X-Conversation-Id", "X-RateLimit-Limit"] 
)

# 2. Middleware Check API Key
@app.middleware("http")
async def api_key_middleware_wrapper(request: Request, call_next):
    # Trình duyệt hỏi đường (CORS) -> Cho qua
    if request.method == "OPTIONS":
        return await call_next(request)
        
    # NẾU LÀ API QUẢN TRỊ ADMIN (CRUD Tenants) HOẶC HEALTH CHECK -> BỎ QUA CHECK API KEY
    path = request.url.path
    if (path.startswith("/tenants") or 
        path.startswith("/health") or 
        path.startswith("/docs") or 
        path.startswith("/ws") or
        path.startswith("/payment")):  # PayMailHook webhook - xác thực bằng secretKey riêng
        return await call_next(request)
        
    # Các API còn lại (Upload, Chat...) -> Bắt buộc kiểm tra API Key
    return await api_key_middleware(request, call_next)

# 3. Đăng ký các Router
app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(user_router)
app.include_router(escalation_router)
app.include_router(tenant_router)
app.include_router(staff_router)
app.include_router(payment_router)

@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "services": {
            "api": "running",
            "redis": "check /stats for details",
            "database": "check by making a request"
        }
    }


@app.get("/stats")
def get_stats():
    """Get system stats"""
    try:
        from core.cache import redis_client
        info = redis_client.info()
        return {
            "redis": {
                "connected": True,
                "memory_used": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients")
            }
        }
    except Exception as e:
        return {
            "redis": {
                "connected": False,
                "error": str(e)
            }
        }