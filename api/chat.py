from openai import OpenAI
from sqlalchemy import text
from core.config import OPENAI_API_KEY, CHAT_MODEL 
from db.session import SessionLocal
from service.embedding import embed_text
from service.rag import retrieve_context
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)

class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    context, images = retrieve_context(req.message)

    prompt = f"""
Bạn là chatbot bán hàng.

Thông tin sản phẩm:
{context}

Câu hỏi khách hàng:
{req.message}
"""

    res = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Bạn là trợ lý bán hàng hữu ích"},
            {"role": "user", "content": prompt}
        ]
    )

    response = {
        "answer": res.choices[0].message.content
    }

    if images:
        response["image_urls"] = images

    return response
