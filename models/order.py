from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.sql import func
from db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    customer_name = Column(String(255))
    customer_phone = Column(String(20))
    customer_email = Column(String(255), nullable=True)
    shipping_address = Column(String(500))
    
    status = Column(String(50), default="draft", index=True)  # draft, confirmed, shipped, completed, cancelled
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
