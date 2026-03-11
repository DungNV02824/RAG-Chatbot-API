from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
from db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    anonymous_id = Column(String, unique=True, index=True) 
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)  # 🔥 QUAN TRỌNG
    full_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True, index=True)  # Removed unique constraint
    email = Column(String(255), nullable=True, index=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

