from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StaffReplyDTO(BaseModel):
    conversation_id: int
    message: str
    staff_name: str

class UpdateEscalationRequest(BaseModel):
    status: str
    assigned_to: Optional[str] = None
    note: Optional[str] = None
    reply: Optional[str] = None 


class StaffReplyRequest(BaseModel):
    message: str
    assigned_to: Optional[str] = None

class EscalationResponse(BaseModel):
    id: int
    conversation_id: int
    user_id: int
    reason: str
    last_message: str
    status: str
    assigned_to: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime
