from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from db.base import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String(20)) 
    content = Column(Text)
    is_staff_reply = Column(Boolean, default=False)  # Đánh dấu tin nhắn từ nhân viên
    staff_name = Column(String(255), nullable=True)  # Tên nhân viên gửi tin nhắn
    created_at = Column(DateTime, server_default=func.now())
