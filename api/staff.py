from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional
from db.session import SessionLocal
from dto.chat_dto import  StaffReplyRequestDTO
from middleware.api_key import get_current_tenant_id
from service.escalation_service import get_active_escalation
from service.message_service import (
    save_message,
    get_recent_messages,
)
from models.escalation import Escalation
from models.user import User
from models.conversation import Conversation
from core.realtime_staff import conversation_connections, broadcast_staff_message


router = APIRouter()


# @router.websocket("/ws/staff-messages/{conversation_id}")
# async def staff_messages_ws(websocket: WebSocket, conversation_id: int):
#     """
#     WebSocket cho phía user subscribe tin nhắn của nhân viên theo conversation_id.
#     """
#     await websocket.accept()
#     cid = int(conversation_id)
#     conversation_connections.setdefault(cid, []).append(websocket)

#     try:
#         # Giữ kết nối mở; client có thể gửi ping, nhưng ta chỉ cần chờ receive.
#         while True:
#             await websocket.receive_text()
#     except WebSocketDisconnect:
#         pass
#     finally:
#         conns = conversation_connections.get(cid, [])
#         if websocket in conns:
#             conns.remove(websocket)
#         if not conns:
#             conversation_connections.pop(cid, None)

# 2. ENDPOINT MỞ KẾT NỐI WS (Cũng bọc ép kiểu String)
@router.websocket("/ws/staff-messages/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    
    # Ép kiểu về str
    cid_str = str(conversation_id)
    
    if cid_str not in conversation_connections:
        conversation_connections[cid_str] = []
    conversation_connections[cid_str].append(websocket)
    
    print(f"\n🟢 [WS KẾT NỐI] Có người VỪA VÀO phòng '{cid_str}'. Tổng số: {len(conversation_connections[cid_str])} người")
    
    try:
        while True:
            # Vòng lặp giữ kết nối không bị văng
            data = await websocket.receive_text()
    except Exception as e:
        print(f"🔴 [WS ĐÓNG] Có người rời phòng '{cid_str}'")
        if websocket in conversation_connections.get(cid_str, []):
            conversation_connections[cid_str].remove(websocket)
        if not conversation_connections.get(cid_str):
            conversation_connections.pop(cid_str, None)

@router.get("/staff/escalations", tags=["Staff Support"])
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
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
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


@router.get("/staff/escalation/{escalation_id}", tags=["Staff Support"])
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
    # 🔐 Import RLS helper
    from db.session import set_tenant_context

    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
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


@router.post("/staff/reply", tags=["Staff Support"])
async def staff_reply(req: StaffReplyRequestDTO, tenant_id: int = Depends(get_current_tenant_id)):
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
    # 🔐 Import RLS helper
    from db.session import set_tenant_context

    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    try:
        print(f" Processing staff reply for conversation #{req.conversation_id}")
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
        
        payload = {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "is_staff_reply": message.is_staff_reply,
            "staff_name": message.staff_name,
            "conversation_id": req.conversation_id,
        }

        # Phát realtime tới phía user nếu có WebSocket đang mở
        await broadcast_staff_message(str(req.conversation_id), payload)

        return {
            "success": True,
            "message": payload,
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


@router.put("/staff/escalation/{escalation_id}/resolve", tags=["Staff Support"])
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
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    from models.escalation import Escalation
    from models.conversation import Conversation
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
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


@router.put("/staff/escalation/{escalation_id}/assign",tags=["Staff Support"])
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
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
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
