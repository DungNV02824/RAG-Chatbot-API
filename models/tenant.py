from sqlalchemy import Column, Integer, String, DateTime, Boolean, Interval
from sqlalchemy.sql import func
from db.base import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)  # Tên web/chatbot
    description = Column(String(500), nullable=True)
    api_key = Column(String(255), unique=True, index=True)  # API key để authenticate
    is_active = Column(Boolean, default=True)

    # PayMailHook config
    pmh_secret_key = Column(String(255), nullable=True, unique=True, index=True)  # Secret Key từ PayMailHook dashboard
    pmh_prefix = Column(String(20), nullable=True)  # Tiền tố mã đơn hàng (VD: "TT")

    # Subscription (gia hạn)
    subscription_expires_at = Column(DateTime, nullable=True)  # NULL = không giới hạn

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
