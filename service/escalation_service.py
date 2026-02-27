from sqlalchemy.orm import Session
from models.escalation import Escalation
from datetime import datetime


def create_escalation(db: Session, conversation_id: int, user_id: int, reason: str, last_message: str):
    """
    Tạo ticket escalation khi cần chuyển nhân viên thực
    
    Args:
        db: Database session
        conversation_id: ID hội thoại
        user_id: ID khách hàng
        reason: Lý do escalate (not_found, customer_request, error)
        last_message: Tin nhắn cuối cùng từ khách
    """
    escalation = Escalation(
        conversation_id=conversation_id,
        user_id=user_id,
        reason=reason,
        last_message=last_message,
        status="pending"
    )
    
    db.add(escalation)
    db.commit()
    db.refresh(escalation)
    
    print(f"✅ Tạo escalation ticket #{escalation.id}")
    return escalation


def get_pending_escalations(db: Session, limit: int = 10):
    """Lấy danh sách ticket chansong chờ xử lý"""
    return db.query(Escalation).filter(
        Escalation.status == "pending"
    ).order_by(Escalation.created_at.desc()).limit(limit).all()


def update_escalation(db: Session, escalation_id: int, status: str, assigned_to: str = None, note: str = None):
    """
    Cập nhật status escalation
    
    Args:
        db: Database session
        escalation_id: ID escalation
        status: pending, in_progress, resolved
        assigned_to: Nhân viên xử lý
        note: Ghi chú từ nhân viên
    """
    escalation = db.query(Escalation).filter(Escalation.id == escalation_id).first()
    
    if not escalation:
        return None
    
    escalation.status = status
    if assigned_to:
        escalation.assigned_to = assigned_to
    if note:
        escalation.note = note
    
    db.commit()
    db.refresh(escalation)
    
    return escalation


def get_escalations_by_user(db: Session, user_id: int):
    """Lấy tất cả escalation của một user"""
    return db.query(Escalation).filter(
        Escalation.user_id == user_id
    ).order_by(Escalation.created_at.desc()).all()


def get_active_escalation(db: Session, conversation_id: int):
    """
    Lấy escalation đang hoạt động (chưa resolved) của conversation
    Dùng để hiển thị thông báo từ nhân viên
    """
    return db.query(Escalation).filter(
        Escalation.conversation_id == conversation_id,
        Escalation.status.in_(["pending", "in_progress"])
    ).order_by(Escalation.created_at.desc()).first()
