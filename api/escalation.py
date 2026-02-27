from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from db.session import SessionLocal
from models.escalation import Escalation
from service.escalation_service import (
    get_pending_escalations,
    update_escalation,
    get_escalations_by_user
)
from service.message_service import save_message

router = APIRouter()


class EscalationResponse(BaseModel):
    id: int
    conversation_id: int
    user_id: int
    reason: str
    last_message: str
    status: str
    assigned_to: Optional[str] = None
    note: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def convert_datetime(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class UpdateEscalationRequest(BaseModel):
    status: str
    assigned_to: Optional[str] = None
    note: Optional[str] = None
    reply: Optional[str] = None  # Phản hồi trực tiếp từ staff


class StaffReplyRequest(BaseModel):
    message: str
    assigned_to: Optional[str] = None


@router.get("/escalations/pending", response_model=List[EscalationResponse])
def get_pending_tickets(limit: int = Query(10, ge=1, le=100)):
    """
    Lấy danh sách ticket escalation chờ xử lý
    """
    db = SessionLocal()
    try:
        escalations = get_pending_escalations(db, limit=limit)
        return escalations
    finally:
        db.close()


@router.put("/escalations/{escalation_id}", response_model=EscalationResponse)
def update_ticket(escalation_id: int, req: UpdateEscalationRequest):
    """
    Cập nhật status escalation ticket
    
    - status: pending, in_progress, resolved
    - assigned_to: Tên nhân viên xử lý
    - note: Ghi chú/lời nhắn cho khách
    """
    db = SessionLocal()
    try:
        escalation = update_escalation(
            db,
            escalation_id,
            req.status,
            req.assigned_to,
            req.note
        )
        
        if not escalation:
            return {"error": "Escalation not found"}, 404
        
        return escalation
    finally:
        db.close()


@router.get("/escalations/user/{user_id}", response_model=List[EscalationResponse])
def get_user_escalations(user_id: int):
    """
    Lấy tất cả escalation của một khách hàng
    """
    db = SessionLocal()
    try:
        escalations = get_escalations_by_user(db, user_id)
        return escalations
    finally:
        db.close()

@router.post("/escalations/{escalation_id}/reply")
def staff_reply_to_customer(escalation_id: int, req: StaffReplyRequest):
    """
    Nhân viên gửi phản hồi trực tiếp cho khách hàng
    Message sẽ được lưu vào conversation và hiển thị ngay trên UI
    
    Args:
        escalation_id: ID của escalation ticket
        req.message: Tin nhắn từ staff
        req.assigned_to: Tên nhân viên (sẽ cập nhật ticket)
    """
    db = SessionLocal()
    try:
        # Lấy escalation để biết conversation_id
        escalation = db.query(Escalation).filter(
            Escalation.id == escalation_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        # Lưu message vào conversation với flag staff_reply
        save_message(db, escalation.conversation_id, "assistant", req.message, is_staff_reply=True, staff_name=req.assigned_to)
        
        # Cập nhật escalation status
        if req.assigned_to:
            escalation.assigned_to = req.assigned_to
        escalation.status = "in_progress"
        escalation.note = req.message
        db.commit()
        db.refresh(escalation)
        
        return {
            "success": True,
            "message": "Phản hồi đã được gửi cho khách hàng",
            "escalation_id": escalation_id,
            "conversation_id": escalation.conversation_id,
            "staff_message": req.message,
            "assigned_to": escalation.assigned_to
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()