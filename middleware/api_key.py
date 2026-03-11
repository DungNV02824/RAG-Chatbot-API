"""
API Key Middleware for Multi-Tenant Support

Maps x-api-key header to tenant_id by looking up in tenants table.
Stores resolved tenant_id in request.state for use in endpoints.
"""

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from db.session import SessionLocal
from models.tenant import Tenant


async def api_key_middleware(request: Request, call_next):
    """
    Middleware to extract x-api-key header and resolve tenant_id.
    
    Flow:
    1. Extract x-api-key from request headers
    2. Look up tenant in database by api_key
    3. Store tenant_id in request.state.tenant_id
    4. If key invalid or tenant inactive, reject with 401
    """
    
    # Get API key from header
    api_key = request.headers.get("x-api-key")
    
    # Some endpoints (like /health) don't require API key
    if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
        request.state.tenant_id = None
        response = await call_next(request)
        return response
    
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
        
        # Store tenant_id in request state for access in endpoints
        request.state.tenant_id = tenant.id
        
    finally:
        db.close()
    
    response = await call_next(request)
    return response


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
    print(" Tenant ID from API key:", tenant_id)
    if tenant_id is None:
        raise HTTPException(
            status_code=401,
            detail="Tenant ID not resolved. Check x-api-key header."
        )
    
    return tenant_id
