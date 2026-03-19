from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from middleware.api_key import api_key_middleware
from api.ingest import router as ingest_router
from api.chat import router as chat_router
from api.list_user import router as user_router
from api.escalation import router as escalation_router
from api.tenant import router as tenant_router

app = FastAPI()

# 1. CORS Middleware phải nằm trên cùng
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "x-api-key"], # Đảm bảo cho phép x-api-key
)

# 2. Middleware Check API Key
@app.middleware("http")
async def api_key_middleware_wrapper(request: Request, call_next):
    # Trình duyệt hỏi đường (CORS) -> Cho qua
    if request.method == "OPTIONS":
        return await call_next(request)
        
    # NẾU LÀ API QUẢN TRỊ ADMIN (CRUD Tenants) HOẶC HEALTH CHECK -> BỎ QUA CHECK API KEY
    path = request.url.path
    if path.startswith("/tenants") or path.startswith("/health"):
        return await call_next(request)
        
    # Các API còn lại (Upload, Chat...) -> Bắt buộc kiểm tra API Key
    return await api_key_middleware(request, call_next)

# 3. Đăng ký các Router
app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(user_router)
app.include_router(escalation_router)
app.include_router(tenant_router)

@app.get("/health")
def health():
    return {"status": "ok"}