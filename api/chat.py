import json
import asyncio
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI

from core.config import OPENAI_API_KEY, CHAT_MODEL
from core.cache import get_cached_response, set_cached_response
from core.rate_limiter import check_rate_limit
from core.queue import enqueue_task, embed_document_task
from db.session import SessionLocal
from service.rag import retrieve_context
from service.intent_service import is_order_intent, is_escalate_intent
from service.context_service import build_context_with_summary
from middleware.api_key import get_current_tenant_id

from service.user_service import get_or_create_user_by_anonymous_id, update_user_profile_from_message
from service.conversation_service import get_or_create_conversation
from service.message_service import (
    save_message,
    get_recent_messages,
    build_chat_history_text
)
 
from service.escalation_service import create_escalation, get_active_escalation

from dto.chat_dto import ChatRequestDTO, DisableBotRequest

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


async def stream_response(prompt, system_content):
    full_response = ""

    try:
        stream = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token

                yield f"event: message\ndata: {json.dumps({'token': token})}\n\n"

        yield f"event: done\ndata: {json.dumps({'full_response': full_response})}\n\n"

    except asyncio.CancelledError:
        yield f"event: error\ndata: {json.dumps({'error': 'cancelled'})}\n\n"
        
    except asyncio.CancelledError:
        # Client disconnected, gracefully stop streaming
        print("⚠️ Streaming cancelled by client")
        yield f"data: {json.dumps({'error': 'Stream cancelled'})}\n\n"
    except Exception as e:
        print(f"❌ Streaming error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@router.post("/chat", tags=["Chat"])
async def chat(req: ChatRequestDTO, tenant_id: int = Depends(get_current_tenant_id)):
    """
    Chat endpoint with optimizations:
    - Rate limiting (Token Bucket)
    - Semantic caching (cache similar questions)
    - Streaming response (SSE for TTFT improvement)
    - Sliding window context (last N messages)
    - Auto summarization for long conversations
    """
    db = SessionLocal()
    
    try:
        # ========== RATE LIMITING ==========
        is_allowed, info = check_rate_limit(
            identifier=f"{tenant_id}:{req.anonymous_id}",
            resource="chat",
            scope="user"
        )
        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail=info.get("message", "Too many requests"),
                headers={
                    "X-RateLimit-Limit": str(info.get("limit", 0)),
                    "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                    "X-RateLimit-Reset": str(info.get("reset_in", 0)),
                    "Retry-After": str(info.get("reset_in", 0))
                }
            )
        
        # ========== SEMANTIC CACHING CHECK ==========
        cached_result = await get_cached_response(tenant_id, req.message)
        if cached_result:
            answer, similarity = cached_result
            print(f"✓ Cache HIT: {similarity:.2%} similar | Latency: <100ms | Cost: $0")
            
            # Still save user message to conversation
            user = get_or_create_user_by_anonymous_id(db, req.anonymous_id, tenant_id)
            conversation = get_or_create_conversation(db, tenant_id, user.id) if user else None
            
            if conversation:
                save_message(db, conversation.id, "user", req.message)
                save_message(db, conversation.id, "assistant", answer)
            
            return {
                "answer": answer,
                "type": "text",
                "cached": True,
                "similarity": similarity
            }
        
        # ========== USER & CONVERSATION ==========
        user = get_or_create_user_by_anonymous_id(db, req.anonymous_id, tenant_id)
        conversation = get_or_create_conversation(db, tenant_id, user.id) if user else None

        if conversation:
            save_message(db, conversation.id, "user", req.message)

        # ========== UPDATE USER PROFILE ==========
        if user and (req.name or req.email or req.address or req.phone):
            print(f"👤 Updating user {user.id}: name={req.name}, email={req.email}")
            
            update_user_profile_from_message(
                db, 
                user, 
                {
                    'name': req.name,
                    'email': req.email,
                    'address': req.address,
                    'phone': req.phone
                }
            )
            
            db.refresh(user)
            print(f"✓ User {user.id} updated: {user.full_name}")

        # ========== CHECK ESCALATION INTENT ==========
        if user and conversation and is_escalate_intent(req.message):
            escalation = create_escalation(
                db,
                conversation.id,
                user.id,
                "customer_request",
                req.message,
                tenant_id
            )
            
            escalate_msg = (
                " Em đã ghi nhận yêu cầu của anh/chị ạ.\n"
                "Hiện tại em đang kết nối với nhân viên support chuyên nghiệp.\n"
                "Anh/chị vui lòng chờ chút xíu nhé!"
            )
            
            save_message(db, conversation.id, "assistant", escalate_msg)
            
            return {
                "answer": escalate_msg,
                "type": "escalated"
            }
        
        # ========== CHECK ORDER INTENT ==========
        if user and conversation and is_order_intent(req.message):
            existing_escalation = get_active_escalation(db, conversation.id)
            if not existing_escalation:
                create_escalation(
                    db,
                    conversation.id,
                    user.id,
                    "new_order_request",
                    "Khách hàng bắt đầu đặt hàng",
                    tenant_id
                )
        
        # ========== CHECK BOT DISABLED ==========
        if conversation and conversation.disable_bot_response:
            print(f" Bot response disabled for conversation #{conversation.id}")
            return {
                "answer": "Nhân viên support sẽ sớm phản hồi lại anh/chị ạ. Vui lòng chờ xíu nhé!",
                "type": "waiting_for_staff"
            }

        # ========== SLIDING WINDOW CONTEXT ==========
        if conversation:
            context_data = build_context_with_summary(db, conversation.id)
            chat_history = context_data["full_context"]
        else:
            chat_history = ""

        # ========== RAG - RETRIEVE CONTEXT ==========
        context, images = retrieve_context(req.message, tenant_id)
        
        if images:
            return {
                "answer": "Dưới đây là hình ảnh sản phẩm anh/chị yêu cầu ạ.",
                "images": images,
                "type": "image"
            }
 
        # ========== NO CONTEXT FOUND - CREATE ESCALATION ==========
        if not context or context.strip() == "":
            print(f" No context found. Creating escalation ticket.")
            
            if conversation:
                try:
                    escalation = create_escalation(
                        db,
                        conversation.id,
                        user.id,
                        "not_found",
                        req.message,
                        tenant_id
                    )
                    print(f"✓ Escalation created: {escalation.id}")
                except Exception as e:
                    print(f"Error creating escalation: {e}")
            
            not_found_msg = (
                "Xin lỗi anh/chị ạ! Em không tìm thấy thông tin chi tiết về vấn đề này. "
                "Để giúp bạn tốt hơn, em đang kết nối với nhân viên support chuyên nghiệp. "
                "Anh/chị vui lòng chờ chút xíu nhé!"
            )
            
            if conversation:
                save_message(db, conversation.id, "assistant", not_found_msg)
            
            return {
                "answer": not_found_msg,
                "type": "escalated"
            }

        # ========== BUILD PROMPT ==========
        prompt = f"""
Thông tin mà em biết:
{context}

Lịch sử trò chuyện:
{chat_history}

Khách vừa nói: {req.message}

Trả lời tự nhiên, như người thực, dựa trên thông tin ở trên.
""".strip()

        system_content = (
            "Bạn là nhân viên chăm sóc khách hàng thân thiện, nhiệt tình. Không phải chatbot lạnh lùng.\n\n"
            "CÁCH CỬ XỬ:\n"
            "- Nói chuyện như người thực, tự nhiên nhất có thể\n"
            "- Xưng 'em' về bản thân, khách là 'anh/chị' (tôn trọng nhưng không quá formal)\n"
            "- Dùng từ tự nhiên: 'ạ', 'nhé' (nhưng không lạm dụng emoji)\n"
            "- Nếu khách hỏi để tìm giải pháp → tư vấn giúp chọn\n"
            "- Nếu khách cần thông tin → cung cấp rõ ràng nhưng không máy móc\n"
            "- Lắng nghe, hiểu nhu cầu thay vì chỉ trả lời câu hỏi\n\n"
            " NGUYÊN TẮC TRẢ LỜI:\n"
            "1.  DÙNG DỮ LIỆU CÓ SẴN: Chỉ nói về những gì em biết từ database\n"
            "2.  KHÔNG SÁNG TẠO: Không bịa ra thông tin, giả định không có cơ sở\n"
            "3.  TỰ NHIÊN NHƯNG CHÍNH XÁC: Nói tự nhiên nhưng phải đúng sự thật\n\n"
            " ĐIỀU CẤMM:\n"
            "- KHÔNG formal hoặc lạnh lùng\n"
            "- KHÔNG viết bullet point khô khan"
        )
        
        # ========== STREAM RESPONSE ==========
        print(f" Streaming response for question: {req.message[:50]}...")
        
        try:
            response = StreamingResponse(
                stream_response(prompt, system_content),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
            
            return response
            
        except asyncio.CancelledError:
            print(" Stream request cancelled")
            return {
                "answer": "Yêu cầu bị hủy. Vui lòng thử lại.",
                "type": "error"
            }

    except asyncio.CancelledError:
        print(" Chat request cancelled")
        raise
    except Exception as e:
        print(f" Chat error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@router.post("/chat/save-response", tags=["Chat"])
async def save_chat_response(
    conversation_id: int,
    answer: str,
    tenant_id: int = Depends(get_current_tenant_id)
):
    """
    Save streamed response to database and cache.
    Call this after streaming completes.
    
    This is needed because streaming responses can't save to DB directly.
    """
    db = SessionLocal()
    try:
        from models.conversation import Conversation
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get the original user question from last message
        messages = get_recent_messages(db, conversation_id, limit=1)
        question = ""
        if messages and messages[-1].role == "user":
            question = messages[-1].content
        
        # Save response
        save_message(db, conversation_id, "assistant", answer)
        
        # Cache the response for semantic similarity matching
        if question:
            await set_cached_response(str(tenant_id), question, answer)
        
        return {
            "success": True,
            "message": "Response saved and cached"
        }
        
    except Exception as e:
        print(f"Error saving response: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/chat/history/{anonymous_id}", tags=["Chat"])
async def get_chat_history(
    anonymous_id: str,
    tenant_id: int = Depends(get_current_tenant_id),
    limit: int = Query(10, ge=1, le=100)
):
    """Get chat history for a user"""
    db = SessionLocal()
    try:
        user = get_or_create_user_by_anonymous_id(db, anonymous_id, tenant_id)
        if not user:
            return {"messages": [], "disable_bot_response": False, "stats": {}}
        
        conversation = get_or_create_conversation(db, tenant_id, user.id)
        if not conversation:
            return {"messages": [], "disable_bot_response": False, "stats": {}}
        
        messages = get_recent_messages(db, conversation.id, limit=limit)
        
        from service.context_service import get_context_stats
        stats = get_context_stats(db, conversation.id)
        
        result = []
        for msg in messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_staff_reply": getattr(msg, 'is_staff_reply', False)
            }
            if getattr(msg, 'is_staff_reply', False):
                msg_dict["staff_name"] = getattr(msg, 'staff_name', None)
            result.append(msg_dict)
        
        return {
            "messages": result,
            "disable_bot_response": conversation.disable_bot_response,
            "stats": stats
        }
    finally:
        db.close()


@router.get("/chat/conversation/{conversation_id}", tags=["Chat"])
async def get_conversation_messages(
    conversation_id: int,
    tenant_id: int = Depends(get_current_tenant_id),
    limit: int = Query(50, ge=1, le=100)
):
    """Get all messages in a conversation (for staff dashboard)"""
    db = SessionLocal()
    try:
        from models.conversation import Conversation
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = get_recent_messages(db, conversation_id, limit=limit)
        
        result = []
        for msg in messages:
            result.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_staff_reply": getattr(msg, 'is_staff_reply', False),
                "staff_name": getattr(msg, 'staff_name', None)
            })
        
        return {
            "conversation_id": conversation_id,
            "messages": result,
            "total_count": len(messages)
        }
        
    finally:
        db.close()


@router.get("/chat/stats/{conversation_id}", tags=["Chat"])
async def get_chat_stats(
    conversation_id: int,
    tenant_id: int = Depends(get_current_tenant_id)
):
    """Get conversation statistics (for optimization monitoring)"""
    db = SessionLocal()
    try:
        from models.conversation import Conversation
        from service.context_service import get_context_stats, get_cached_summary
        from service.summarization_service import get_summary_stats
        from core.cache import get_cache_stats
        from core.rate_limiter import get_rate_limit_status
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        context_stats = get_context_stats(db, conversation_id)
        summary_stats = get_summary_stats(db, conversation_id)
        cache_stats = get_cache_stats(int(tenant_id))
        rate_stats = get_rate_limit_status(str(tenant_id), "chat")
        
        return {
            "conversation_id": conversation_id,
            "context": context_stats,
            "summarization": summary_stats,
            "cache": cache_stats,
            "rate_limiting": rate_stats
        }
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/chat/disable-bot/{conversation_id}", tags=["Chat"])
async def disable_bot_response(
    conversation_id: int,
    req: DisableBotRequest,
    tenant_id: int = Depends(get_current_tenant_id)
):
    """Disable bot responses for a conversation (when escalated to staff)"""
    db = SessionLocal()
    try:
        from models.conversation import Conversation
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        conversation.disable_bot_response = req.disable
        db.commit()
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "bot_disabled": req.disable
        }
        
    finally:
        db.close()
