from openai import OpenAI
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from core.config import OPENAI_API_KEY, CHAT_MODEL
from db.session import SessionLocal
from service.rag import retrieve_context
from service.user_service import (
    update_user_profile_from_message,
    get_or_create_user_by_anonymous_id
)
from service.conversation_service import get_or_create_conversation
from service.message_service import (
    save_message,
    get_recent_messages,
    build_chat_history_text
)

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


class ChatRequest(BaseModel):
    message: str
    anonymous_id: Optional[str] = None


@router.post("/chat")
def chat(req: ChatRequest):
    db = SessionLocal()

    try:
        user = get_or_create_user_by_anonymous_id(db, req.anonymous_id)
        update_user_profile_from_message(db, user, req.message)

        user_id = user.id if user else None
        conversation = get_or_create_conversation(db, user_id) if user_id else None

        if conversation:
            save_message(db, conversation.id, "user", req.message)

        chat_history = ""
        if conversation:
            messages = get_recent_messages(db, conversation.id, limit=6)
            chat_history = build_chat_history_text(messages)

        context, images = retrieve_context(req.message)

        # =========================
        # IMAGE INTENT → TRẢ ẢNH NGAY
        # =========================
        if images:
            answer = "Dưới đây là hình ảnh sản phẩm bạn yêu cầu."

            if conversation:
                save_message(db, conversation.id, "assistant", answer)

            return {
                "answer": answer,
                "images": images,
                "user_id": user_id,
                "conversation_id": conversation.id if conversation else None
            }

        # =========================
        # TEXT INTENT → GỌI LLM
        # =========================
        prompt = f"""
Bạn là chatbot bán hàng.

Lịch sử hội thoại:
{chat_history}

Thông tin sản phẩm:
{context}

Câu hỏi hiện tại của khách hàng:
{req.message}
"""

        res = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là trợ lý bán hàng. Chỉ trả lời dựa trên dữ liệu được cung cấp. Không bịa."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        answer = res.choices[0].message.content

        if conversation:
            save_message(db, conversation.id, "assistant", answer)

        return {
            "answer": answer,
            "user_id": user_id,
            "conversation_id": conversation.id if conversation else None
        }

    finally:
        db.close()
