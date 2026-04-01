from fastapi import APIRouter, Query, HTTPException
from pydantic import field_validator
from typing import List
from datetime import datetime
from db.session import SessionLocal
from models.escalation import Escalation
from dto.staff_reply_dto import UpdateEscalationRequest, StaffReplyRequest, EscalationResponse

from service.escalation_service import (
    get_pending_escalations,
    update_escalation,
    get_escalations_by_user
)
from service.message_service import save_message
from core.realtime_staff import broadcast_staff_message

router = APIRouter()

class Config:
    from_attributes = True

    @field_validator('created_at', 'updated_at', mode='before')
    @classmethod
    def convert_datetime(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v


@router.get("/escalations/pending", response_model=List[EscalationResponse], tags=["Escalation"])
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


@router.put("/escalations/{escalation_id}", response_model=EscalationResponse, tags=["Escalation"])
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


@router.get("/escalations/user/{user_id}", response_model=List[EscalationResponse], tags=["Escalation"])
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

@router.post("/escalations/{escalation_id}/reply", tags=["Escalation"])
async def staff_reply_to_customer(escalation_id: int, req: StaffReplyRequest):
    """
    Staff trả lời khách
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
            print(f" Escalation #{escalation_id} not found")
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        print(f" Processing staff reply for escalation #{escalation_id}")
        print(f"   - Conversation ID: {escalation.conversation_id}")
        print(f"   - Staff: {req.assigned_to}")
        print(f"   - Message: {req.message[:50]}..." if len(req.message) > 50 else f"   - Message: {req.message}")
        
        # Lưu message vào conversation với flag staff_reply
        try:
            message = save_message(db, escalation.conversation_id, "assistant", req.message, is_staff_reply=True, staff_name=req.assigned_to)
            print(f" Message #{message.id} saved to conversation #{escalation.conversation_id}")
        except Exception as msg_error:
            print(f" Error saving message: {msg_error}")
            import traceback
            traceback.print_exc()
            raise
        
        # Cập nhật escalation status
        if req.assigned_to:
            escalation.assigned_to = req.assigned_to
        escalation.status = "in_progress"
        escalation.note = req.message

        try:
            db.commit()
            db.refresh(escalation)
            print(f" Escalation #{escalation_id} updated successfully")
        except Exception as commit_error:
            print(f" Error committing escalation update: {commit_error}")
            import traceback
            traceback.print_exc()
            raise

        # Broadcast realtime cho phía user (giống /staff/reply)
        try:
            payload = {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "is_staff_reply": message.is_staff_reply,
                "staff_name": message.staff_name,
                "conversation_id": escalation.conversation_id,
            }
            await broadcast_staff_message(escalation.conversation_id, payload)
        except Exception as br_err:
            # Không fail API nếu broadcast lỗi; chỉ log
            print(f"⚠️ Error broadcasting staff reply WS: {br_err}")
        
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
        print(f" Error in staff_reply_to_customer: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        db.close()