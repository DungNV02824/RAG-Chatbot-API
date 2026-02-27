from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from db.base import Base


class Escalation(Base):
    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    reason = Column(String(500))  # "not_found", "customer_request", "error"
    last_message = Column(Text)  # Tin nhắn cuối cùng của khách
    status = Column(String(50), default="pending", index=True)  # pending, in_progress, resolved
    
    assigned_to = Column(String(255), nullable=True)  # Nhân viên xử lý
    note = Column(Text, nullable=True)  # Ghi chú từ nhân viên
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
