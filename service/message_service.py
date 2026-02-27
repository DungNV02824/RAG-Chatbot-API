from sqlalchemy.orm import Session
from models.message import Message

def save_message(db: Session, conversation_id: int, role: str, content: str, is_staff_reply: bool = False, staff_name: str = None):
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        is_staff_reply=is_staff_reply,
        staff_name=staff_name
    )
    db.add(msg)
    db.commit()
    return msg


def get_recent_messages(
    db: Session,
    conversation_id: int,
    limit: int = 6
):
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )

    return list(reversed(messages))  # đảo lại cho đúng thứ tự

def build_chat_history_text(messages):
    history = ""
    for msg in messages:
        role = "Khách hàng" if msg.role == "user" else "Trợ lý"
        history += f"{role}: {msg.content}\n"
    return history.strip()
