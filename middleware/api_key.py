"""
API Key Middleware for Multi-Tenant Support with RLS

Maps x-api-key header to tenant_id by looking up in tenants table.
Stores resolved tenant_id in request.state for use in endpoints.
Sets PostgreSQL RLS context (app.current_tenant) for data isolation.
"""

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.session import SessionLocal
from models.tenant import Tenant
# File: middleware/api_key.py

async def api_key_middleware(request: Request, call_next):
    """
    Middleware to extract x-api-key header and resolve tenant_id with RLS context.
    """
    
    # 1. CẬP NHẬT TẠI ĐÂY: Thêm "/payment" vào danh sách các đường dẫn không check x-api-key header
    # Sử dụng .startswith để bao quát cả /payment/webhook và các route con khác của payment
    if (request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"] or 
        request.url.path.startswith("/payment")):
        
        request.state.tenant_id = None
        request.state.rls_context_set = False
        response = await call_next(request)
        return response
    
    # --- PHẦN CÒN LẠI GIỮ NGUYÊN ---
    
    # Get API key from header
    api_key = request.headers.get("x-api-key")
    
    # API key is required for all other endpoints
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing x-api-key header"
        )
    
    # Look up tenant by API key
    db: Session = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(
            Tenant.api_key == api_key,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key or tenant is inactive"
            )
        
        # 🔐 SET RLS CONTEXT: Configure PostgreSQL session variable
        try:
            db.execute(
                text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
                {"tenant_id": str(tenant.id)},
            )
            # Optional backward-compatible key.
            db.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
                {"tenant_id": str(tenant.id)},
            )
            print(f"🔐 RLS context set: app.current_tenant = {tenant.id}")
        except Exception as rls_error:
            print(f"⚠️ Warning: RLS context not set: {rls_error}")
        
        request.state.tenant_id = tenant.id
        request.state.rls_context_set = True
        print(f"✓ Tenant authenticated: {tenant.id} ({tenant.name})")
        
    finally:
        db.close()
    
    response = await call_next(request)
    return response

# async def api_key_middleware(request: Request, call_next):
#     """
#     Middleware to extract x-api-key header and resolve tenant_id with RLS context.
    
#     Flow:
#     1. Extract x-api-key from request headers
#     2. Look up tenant in database by api_key
#     3. Set PostgreSQL RLS context (app.current_tenant)
#     4. Store tenant_id in request.state.tenant_id
#     5. If key invalid or tenant inactive, reject with 401
#     """
    
#     # Get API key from header
#     api_key = request.headers.get("x-api-key")
    
#     # Some endpoints (like /health) don't require API key
#     if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
#         request.state.tenant_id = None
#         request.state.db = None
#         response = await call_next(request)
#         return response
    
#     # API key is required for all other endpoints
#     if not api_key:
#         raise HTTPException(
#             status_code=401,
#             detail="Missing x-api-key header"
#         )
    
#     # Look up tenant by API key
#     db: Session = SessionLocal()
#     try:
#         tenant = db.query(Tenant).filter(
#             Tenant.api_key == api_key,
#             Tenant.is_active == True
#         ).first()
        
#         if not tenant:
#             raise HTTPException(
#                 status_code=401,
#                 detail="Invalid API key or tenant is inactive"
#             )
        
#         # 🔐 SET RLS CONTEXT: Configure PostgreSQL session variable
#         try:
#             db.execute(
#                 text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
#                 {"tenant_id": str(tenant.id)},
#             )
#             # Optional backward-compatible key.
#             db.execute(
#                 text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
#                 {"tenant_id": str(tenant.id)},
#             )
#             print(f"🔐 RLS context set: app.current_tenant = {tenant.id}")
#         except Exception as rls_error:
#             print(f"⚠️ Warning: RLS context not set: {rls_error}")
#             # Don't fail the request - RLS has default policies
        
#         # Store tenant_id and db in request state for access in endpoints
#         request.state.tenant_id = tenant.id
#         request.state.rls_context_set = True
        
#         print(f"✓ Tenant authenticated: {tenant.id} ({tenant.name})")
        
#     finally:
#         db.close()
    
#     response = await call_next(request)
#     return response


def get_current_tenant_id(request: Request) -> int:
    """
    Dependency injection to get the resolved tenant_id from request.
    
    Usage in endpoints:
        @router.get("/some-endpoint")
        def some_endpoint(tenant_id: int = Depends(get_current_tenant_id)):
            # tenant_id is automatically resolved from x-api-key
            pass
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    rls_set = getattr(request.state, "rls_context_set", False)
    
    print(f"📌 Tenant ID from API key: {tenant_id} (RLS context: {'✓' if rls_set else '✗'})")
    
    if tenant_id is None:
        raise HTTPException(
            status_code=401,
            detail="Tenant ID not resolved. Check x-api-key header."
        )
    
    return tenant_id
