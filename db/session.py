from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from db.base import engine
from typing import Optional

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def set_tenant_context(db_session, tenant_id: int):
    """
    Set PostgreSQL session variable for RLS (Row Level Security).
    
    This should be called immediately after getting a database session
    to enable RLS policies that check app.current_tenant.
    
    Args:
        db_session: SQLAlchemy session object
        tenant_id: The tenant ID to set in PostgreSQL session context
    """
    try:
        # Execute SQL to set session variable for RLS.
        # Keep both keys for backward compatibility with older DB scripts.
        db_session.execute(
            text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
            {"tenant_id": str(tenant_id)},
        )
        db_session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
            {"tenant_id": str(tenant_id)},
        )
        print(f"✓ PostgreSQL RLS context set: app.current_tenant = {tenant_id}")
    except Exception as e:
        print(f"⚠️ Failed to set RLS context: {e}")
        # Don't raise - allow request to continue
        # RLS will fall back to default permissions if context not set

def get_db():
    """
    Get database session.
    Note: Call set_tenant_context() immediately after getting this session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_with_tenant(tenant_id: int):
    """
    Get database session with RLS context pre-configured.
    
    Args:
        tenant_id: The tenant ID for RLS context
    
    Returns:
        Configured SQLAlchemy session
    """
    db = SessionLocal()
    set_tenant_context(db, tenant_id)
    return db
