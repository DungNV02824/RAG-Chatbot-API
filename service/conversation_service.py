from sqlalchemy.orm import Session
from models.conversation import Conversation

from models.message import Message

def get_or_create_conversation(db, user_id: int):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .first()
    )

    if conversation:
        return conversation

    conversation = Conversation(
        user_id=user_id,
        # title="New chat"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation
