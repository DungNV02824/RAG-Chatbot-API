from openai import OpenAI
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from core.config import OPENAI_API_KEY, CHAT_MODEL
from db.session import SessionLocal
from service.rag import retrieve_context
from service.intent_service import is_order_intent, is_escalate_intent
from middleware.api_key import get_current_tenant_id

from service.user_service import get_or_create_user_by_anonymous_id, update_user_profile_from_message
from service.conversation_service import get_or_create_conversation
from service.message_service import (
    save_message,
    get_recent_messages,
    build_chat_history_text
)
from service.order_state_service import update_user_by_order_step
from service.order_flow import get_next_order_step, get_order_step_question
from service.order_validator import is_answer_for_order_step
from service.escalation_service import create_escalation, get_active_escalation

from dto.chat_dto import ChatRequestDTO, StaffReplyRequestDTO, DisableBotRequest

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


@router.post("/chat",  tags=["chat"])
def chat(req: ChatRequestDTO, tenant_id: int = Depends(get_current_tenant_id)):
    db = SessionLocal()

    try:
        #USER & CONVERSATION 
        user = get_or_create_user_by_anonymous_id(db, req.anonymous_id, tenant_id)
        conversation = get_or_create_conversation(db, tenant_id, user.id) if user else None

        if conversation:
            save_message(db, conversation.id, "user", req.message)

        # CẬP NHẬT THÔNG TIN KHÁCH HÀNG 
        if user and (req.name or req.email or req.address or req.phone):
            print(f" Cập nhật user {user.id}: name={req.name}, email={req.email}, phone={req.phone}, address={req.address}")
            
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
            
            # Force reload từ database
            db.refresh(user)
            print(f"User {user.id} được cập nhật: full_name={user.full_name}, phone={user.phone}, email={user.email}, address={user.address}")

        
        # CHECK USER MUỐN ESCALATE (CHUYỂN NHÂN VIÊN)
        if user and conversation and is_escalate_intent(req.message):
            # User muốn nói chuyện với nhân viên thực
            escalation = create_escalation(
                db,
                conversation.id,
                user.id,
                "customer_request",
                req.message,
                tenant_id
            )
            
            escalate_msg = (
                " Em đã ghi nhận yêu cầu của anh/chị ạ. \n"
                "Hiện tại em đang kết nối với nhân viên support chuyên nghiệp. \n"
                "Anh/chị vui lòng chờ chút xíu nhé!"
            )
            
            save_message(db, conversation.id, "assistant", escalate_msg)
            
            return {
                "answer": escalate_msg,
                "type": "escalated"
            }
        
        if user and conversation and is_order_intent(req.message):

            #  Nếu chưa có escalation thì mới tạo
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
        # CHECK BOT RESPONSE CÓ BỊ TẮT KHÔNG
        if conversation and conversation.disable_bot_response:
            print(f" Bot response bị tắt cho conversation #{conversation.id}")
            # Không trả lời gì, chỉ lưu message
            # Nhân viên sẽ trả lời trực tiếp
            return {
                "answer": "Nhân viên support sẽ sớm phản hồi lại anh/chị ạ. Vui lòng chờ xíu nhé!",
                "type": "waiting_for_staff"
            }

        # LỊCH SỬ HỘI THOẠI
        chat_history = ""
        if conversation:
            messages = get_recent_messages(db, conversation.id, limit=6)
            chat_history = build_chat_history_text(messages)

        # RAG (TÌM KIẾM SẢN PHẨM) 
        context, images = retrieve_context(req.message, tenant_id)
        if images:
            return {
                "answer": "Dưới đây là hình ảnh sản phẩm anh/chị yêu cầu ạ.",
                "images": images,
                "type": "image"
            }
 
        #  KIỂM TRA NẾU KHÔNG CÓ THÔNG TIN TRONG DATABASE 
        if not context or context.strip() == "":
            print(f"DEBUG: Context rỗng, tạo escalation ticket")
            print(f"   - conversation: {conversation}")
            print(f"   - user: {user}")
            
            # Tạo escalation ticket
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
                    print(f" Escalation ticket created: {escalation.id}")
                except Exception as e:
                    print(f" Error creating escalation: {e}")
                    import traceback
                    traceback.print_exc()
            
            not_found_msg = (
                "Xin lỗi anh/chị ạ!  Em không tìm thấy thông tin chi tiết về vấn đề này trong cơ sở dữ liệu của em. \n\n"
                "Để có thể hỗ trợ anh/chị tốt hơn, em đang kết nối với nhân viên support chuyên nghiệp. "
                "Anh/chị vui lòng chờ chút xíu nhé! Cảm ơn anh/chị rất nhiều. "
            )
            
            if conversation:
                save_message(db, conversation.id, "assistant", not_found_msg)
            
            return {
                "answer": not_found_msg,
                "type": "escalated"
            }

        # LLM CHAT (TRẢ LỜI DỰA TRÊN DATASET) 
        prompt = f"""
Thông tin mà em biết:
{context}

Lịch sử trò chuyện trước đó:
{chat_history}

Khách vừa nói: {req.message}

Trả lời tự nhiên, như người thực, dựa HOÀN TOÀN trên thông tin ở trên.
""".strip()

        res = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là nhân viên chăm sóc khách hàng thân thiện, nhiệt tình. Không phải chatbot lạnh lùng.\n\n"
                        "🎯 CÁCH CỬ XỬ:\n"
                        "- Nói chuyện như người thực, tự nhiên nhất có thể\n"
                        "- Xưng 'em' về bản thân, khách là 'anh/chị' (tôn trọng nhưng không quá formal)\n"
                        "- Dùng từ tự nhiên: 'ạ', 'nhé', '😊' (nhưng không lạm dụng emoji)\n"
                        "- Nếu khách hỏi để tìm giải pháp → tư vấn giúp chọn\n"
                        "- Nếu khách cần thông tin → cung cấp rõ ràng nhưng không máy móc\n"
                        "- Lắng nghe, hiểu nhu cầu thay vì chỉ trả lời câu hỏi\n\n"
                        "💎 NGUYÊN TẮC TRẢ LỜI:\n"
                        "1. ✅ DÙNG DỮ LIỆU CÓ SẴN: Chỉ nói về những gì em biết từ database\n"
                        "2. ❌ KHÔNG SÁNG TẠO: Không bịa ra thông tin, giả định không có cơ sở\n"
                        "3. ✅ TỰ NHIÊN NHƯNG CHÍNH XÁC: Nói tự nhiên nhưng phải đúng sự thật\n"
                        "4. ✅ TƯ VẤN THỰC SỰ: Giúp khách quyết định, không chỉ liệt kê\n"
                        "5. ✅ THẤU HIỂU: Nếu khách hỏi điều em không biết → thành thật nói ra\n\n"
                        "💬 VÍ DỤ CỬ XỬ TỰ NHIÊN:\n"
                        "❌ Sai: 'Sản phẩm A có tính năng 1, tính năng 2, tính năng 3. Giá 100k.'\n"
                        "✅ Đúng: 'Sản phẩm A khá hot hiện tại ạ. Nó có điểm mạnh là có tính năng 1, "\
                        "tính năng 2, nên rất phù hợp nếu anh/chị cần... Giá là 100k. Anh/chị có muốn tìm hiểu thêm không?'\n\n"
                        "❌ Sai: 'Xin lỗi em chưa có thông tin về vấn đề này.'\n"
                        "✅ Đúng: 'Thôi em phải thành thật nói là em chưa gặp câu hỏi này bao giờ. "\
                        "Anh/chị có thể kiện lại với nhân viên chuyên môn em kết nối nhé?'\n\n"
                        "⚠️ ĐIỀU CẤMM:\n"
                        "- KHÔNG nói 'có thể', 'có lẽ', 'mình nghĩ' về thông tin không chắc\n"
                        "- KHÔNG viết kiểu bullet point khô Khan, giống danh sách\n"
                        "- KHÔNG emoji quá nhiều (tối đa 1-2 emoji/message)\n"
                        "- KHÔNG formal hoặc lạnh lùng\n\n"
                        "🎯 MỤC TIÊU: Khách cảm thấy đang chat với người thực, không phải bot"
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        answer = res.choices[0].message.content.strip()
        
        #  LOG để verify LLM dùng dữ liệu từ database
        print(f"📊 DEBUG - Chat Response:")
        print(f"   Context length: {len(context)} chars")
        print(f"   Answer length: {len(answer)} chars")
        print(f"   Answer: {answer[:100]}...")

        if conversation:
            save_message(db, conversation.id, "assistant", answer)

        # PHẢN HỒI NHÂN VIÊN (NẾU CÓ ESCALATION) 
        response_data = {
            "answer": answer,
            "type": "text"
        }
        # Check xem có escalation với staff note không
        if conversation:
            active_escalation = get_active_escalation(db, conversation.id)
            if active_escalation and active_escalation.note:
                response_data["staff_notification"] = {
                    "assigned_to": active_escalation.assigned_to,
                    "status": active_escalation.status,
                    "note": active_escalation.note
                }

        return response_data

    finally:
        db.close()


@router.get("/chat/history/{anonymous_id}", tags=["chat"])
def get_chat_history(anonymous_id: str, tenant_id: int = Depends(get_current_tenant_id), limit: int = Query(10, ge=1, le=100)):
    """
    Lấy lịch sử chat (recent messages) của user
    Dùng để frontend auto-refresh khi có staff phản hồi
    
    Response:
    {
        "messages": [...],
        "disable_bot_response": true/false
    }
    """
    db = SessionLocal()
    try:
        user = get_or_create_user_by_anonymous_id(db, anonymous_id, tenant_id)
        if not user:
            return {"messages": [], "disable_bot_response": False}
        
        conversation = get_or_create_conversation(db, tenant_id, user.id)
        if not conversation:
            return {"messages": [], "disable_bot_response": False}
        
        messages = get_recent_messages(db, conversation.id, limit=limit)
        result = []
        for msg in reversed(messages):  # Reverse để oldest message first
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_staff_reply": getattr(msg, 'is_staff_reply', False)
            }
            # Thêm thông tin nhân viên nếu có
            if getattr(msg, 'is_staff_reply', False):
                msg_dict["staff_name"] = getattr(msg, 'staff_name', None)
            result.append(msg_dict)
        
        return {
            "messages": result,
            "disable_bot_response": conversation.disable_bot_response
        }
    finally:
        db.close()


@router.get("/chat/conversation/{conversation_id}", tags=["chat"])
def get_conversation_messages(conversation_id: int, tenant_id: int = Depends(get_current_tenant_id), limit: int = Query(50, ge=1, le=100)):
    """
    Lấy lịch sử chat của một cuộc hội thoại (conversation)
    Được dùng bởi staff dashboard để xem tin nhắn trong ticket escalation
    
    Args:
        conversation_id: ID của conversation
        tenant_id: ID của tenant (được resolve từ x-api-key)
        limit: Số lượng tin nhắn tối đa muốn lấy
    
    Response:
    {
        "messages": [...],
        "disable_bot_response": true/false
    }
    """
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        messages = get_recent_messages(db, conversation_id, limit=limit)
        result = []
        for msg in reversed(messages):
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            # Thêm thông tin nhân viên nếu có
            if hasattr(msg, 'is_staff_reply') and msg.is_staff_reply:
                msg_dict["is_staff_reply"] = True
                msg_dict["staff_name"] = msg.staff_name
            else:
                msg_dict["is_staff_reply"] = False
            result.append(msg_dict)
        
        return {
            "messages": result,
            "disable_bot_response": conversation.disable_bot_response if conversation else False
        }
    finally:
        db.close()


# =========================================================
# ===== STAFF SUPPORT ENDPOINTS ===========================
# =========================================================

@router.get("/staff/escalations")
def get_escalations_list(tenant_id: int = Depends(get_current_tenant_id), status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=100)):
    """
    Lấy danh sách tất cả escalation tickets cần hỗ trợ cho tenant
    
    Query params:
        - status: 'pending', 'in_progress', 'resolved' (nếu không có thì lấy tất cả)
        - limit: số lượng ticket tối đa
    
    Response:
    {
        "escalations": [
            {
                "id": 1,
                "conversation_id": 100,
                "user_id": 5,
                "type": "not_found",
                "status": "pending",
                "reason": "Khách hỏi điều gì không có trong DB",
                "customer_message": "...",
                "created_at": "...",
                "assigned_to": null,
                "user_info": {
                    "name": "Nguyễn Văn A",
                    "email": "a@example.com",
                    "phone": "0123456789"
                }
            }
        ]
    }
    """
    from models.escalation import Escalation
    from models.user import User
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        query = db.query(Escalation).join(Conversation).filter(
            Conversation.tenant_id == tenant_id
        ).order_by(Escalation.created_at.desc())
        
        if status:
            query = query.filter(Escalation.status == status)
        
        escalations = query.limit(limit).all()
        
        result = []
        for esc in escalations:
            user = db.query(User).filter(User.id == esc.user_id).first()
            conversation = db.query(Conversation).filter(Conversation.id == esc.conversation_id).first()
            result.append({
                "id": esc.id,
                "conversation_id": esc.conversation_id,
                "user_id": esc.user_id,
                "type": esc.reason,  # 'not_found', 'customer_request', 'new_order_request'
                "status": esc.status,
                "reason": esc.reason,
                "customer_message": esc.last_message,  # Message từ khách
                "created_at": esc.created_at.isoformat() if esc.created_at else None,
                "assigned_to": esc.assigned_to,
                "disable_bot_response": conversation.disable_bot_response if conversation else False,
                "user_info": {
                    "id": user.id,
                    "name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "address": user.address
                } if user else None
            })
        
        return {"escalations": result}
    finally:
        db.close()


@router.get("/staff/escalation/{escalation_id}")
def get_escalation_detail(escalation_id: int, tenant_id: int = Depends(get_current_tenant_id)):
    """
    Xem chi tiết một escalation ticket và lịch sử chat
    
    Response:
    {
        "escalation": {
            "id": 1,
            "conversation_id": 100,
            "status": "pending",
            "type": "not_found",
            "created_at": "...",
            "assigned_to": "Nhân viên A"
        },
        "user": {
            "id": 5,
            "name": "Nguyễn Văn A",
            "email": "a@example.com",
            "phone": "0123456789",
            "address": "123 Đường ABC"
        },
        "messages": [
            {"role": "user", "content": "...", "created_at": "...", "is_staff_reply": false},
            {"role": "assistant", "content": "...", "created_at": "...", "is_staff_reply": false},
            ...
        ]
    }
    """
    from models.escalation import Escalation
    from models.user import User
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        # Join với conversation để verify tenant
        escalation = db.query(Escalation).join(Conversation).filter(
            Escalation.id == escalation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        user = db.query(User).filter(User.id == escalation.user_id).first()
        
        # Lấy lịch sử chat
        messages = get_recent_messages(db, escalation.conversation_id, limit=100)
        
        messages_list = []
        for msg in reversed(messages):
            msg_dict = {
                "id": msg.id if hasattr(msg, 'id') else None,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "is_staff_reply": getattr(msg, 'is_staff_reply', False)
            }
            if getattr(msg, 'is_staff_reply', False):
                msg_dict["staff_name"] = getattr(msg, 'staff_name', None)
            messages_list.append(msg_dict)
        
        return {
            "escalation": {
                "id": escalation.id,
                "conversation_id": escalation.conversation_id,
                "status": escalation.status,
                "type": escalation.reason,
                "reason": escalation.reason,
                "created_at": escalation.created_at.isoformat() if escalation.created_at else None,
                "assigned_to": escalation.assigned_to,
                "note": escalation.note
            },
            "user": {
                "id": user.id,
                "name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "address": user.address
            } if user else None,
            "messages": messages_list
        }
    finally:
        db.close()


@router.post("/staff/reply")
def staff_reply(req: StaffReplyRequestDTO, tenant_id: int = Depends(get_current_tenant_id)):
    """
    Nhân viên trả lời khách hàng trong một cuộc hội thoại (conversation)
    
    Request:
    {
        "conversation_id": 100,
        "message": "Trả lời của nhân viên",
        "staff_name": "Nguyễn Văn B"
    }
    
    Response:
    {
        "success": true,
        "message_id": 123,
        "conversation_id": 100,
        "staff_name": "Nguyễn Văn B"
    }
    """
    from models.escalation import Escalation
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        print(f"📝 Processing staff reply for conversation #{req.conversation_id}")
        print(f"   - Tenant ID: {tenant_id}")
        print(f"   - Staff: {req.staff_name}")
        print(f"   - Message: {req.message[:50]}..." if len(req.message) > 50 else f"   - Message: {req.message}")
        
        # Fetch conversation với tenant verification
        conversation = db.query(Conversation).filter(
            Conversation.id == req.conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            print(f" Conversation #{req.conversation_id} not found for tenant {tenant_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        print(f" Conversation #{req.conversation_id} found")
        print(f"   - User ID: {conversation.user_id}")
        
        # Lưu tin nhắn của nhân viên
        try:
            message = save_message(
                db,
                req.conversation_id,
                "assistant",
                req.message,
                is_staff_reply=True,
                staff_name=req.staff_name
            )
            print(f"Message #{message.id} saved to conversation #{req.conversation_id}")
        except Exception as msg_err:
            print(f" Error saving message: {msg_err}")
            import traceback
            traceback.print_exc()
            raise
        
        # Cập nhật escalation nếu có active escalation
        active_escalation = get_active_escalation(db, req.conversation_id)
        if active_escalation:
            active_escalation.status = "in_progress"
            active_escalation.assigned_to = req.staff_name
            active_escalation.note = req.message
            
            try:
                db.commit()
                db.refresh(active_escalation)
                print(f" Escalation #{active_escalation.id} updated successfully")
            except Exception as commit_err:
                print(f" Error updating escalation: {commit_err}")
                import traceback
                traceback.print_exc()
                raise
        else:
            db.commit()
            print(f" No active escalation for conversation #{req.conversation_id}")
        
        return {
            "success": True,
            # "message_id": message.id if hasattr(message, 'id') else None,
            # "conversation_id": req.conversation_id,
            # "staff_name": req.staff_name
             "message": {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "is_staff_reply": message.is_staff_reply,
                "staff_name": message.staff_name
                        }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f" Unexpected error in staff reply: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        db.close()


@router.put("/staff/escalation/{escalation_id}/resolve")
def resolve_escalation(escalation_id: int, tenant_id: int = Depends(get_current_tenant_id), resolution_note: Optional[str] = Query(None)):
    """
    Đánh dấu escalation ticket là đã giải quyết
    
    Response:
    {
        "success": true,
        "escalation": {
            "id": 1,
            "status": "resolved",
            "resolved_at": "..."
        }
    }
    """
    from models.escalation import Escalation
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        escalation = db.query(Escalation).join(Conversation).filter(
            Escalation.id == escalation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        escalation.status = "resolved"
        if resolution_note:
            escalation.note = resolution_note
        
        db.add(escalation)
        db.commit()
        
        print(f" Escalation #{escalation_id} marked as resolved")
        
        return {
            "success": True,
            "escalation": {
                "id": escalation.id,
                "status": escalation.status,
                "resolved_at": escalation.created_at.isoformat() if escalation.created_at else None
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.put("/staff/escalation/{escalation_id}/assign")
def assign_escalation(escalation_id: int, tenant_id: int = Depends(get_current_tenant_id), staff_name: str = Query(...)):
    """
    Gán escalation ticket cho nhân viên cụ thể
    
    Query params:
        - staff_name: Tên nhân viên
    
    Response:
    {
        "success": true,
        "escalation": {
            "id": 1,
            "assigned_to": "Nguyễn Văn B"
        }
    }
    """
    from models.escalation import Escalation
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        escalation = db.query(Escalation).join(Conversation).filter(
            Escalation.id == escalation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        escalation.assigned_to = staff_name
        escalation.status = "in_progress"
        
        db.add(escalation)
        db.commit()
        
        print(f" Escalation #{escalation_id} assigned to {staff_name}")
        
        return {
            "success": True,
            "escalation": {
                "id": escalation.id,
                "assigned_to": escalation.assigned_to,
                "status": escalation.status
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()





@router.post("/chat/conversation/{conversation_id}/disable-bot", tags=["chat"])
def disable_bot_response(conversation_id: int, req: DisableBotRequest, tenant_id: int = Depends(get_current_tenant_id)):
    """
    Tắt/bật bot response cho một conversation cụ thể
    
    Body:
    {
        "is_disabled": true/false
    }
    
    Response:
    {
        "success": true,
        "conversation_id": 1,
        "disable_bot_response": true
    }
    """
    from models.conversation import Conversation
    
    db = SessionLocal()
    try:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        conversation.disable_bot_response = req.is_disabled
        db.add(conversation)
        db.commit()
        
        status_msg = "tắt" if req.is_disabled else "bật"
        print(f" Bot response đã được {status_msg} cho conversation #{conversation_id}")
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "disable_bot_response": conversation.disable_bot_response
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()