from pydantic import BaseModel
from typing import Optional

class ChatRequestDTO(BaseModel):
    message: str
    anonymous_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

class StaffReplyRequestDTO(BaseModel):
    conversation_id: int
    message: str
    staff_name: Optional[str] = None