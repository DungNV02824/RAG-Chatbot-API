from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from service.user_service import get_all_users, get_or_create_user_by_anonymous_id, update_user_profile_from_message, delete_user_with_cascading
from db.session import SessionLocal
from middleware.api_key import get_current_tenant_id
from sqlalchemy import desc
from models.message import Message
from dto.user_dto import UserInfoUpdate

router = APIRouter()

@router.post("/users/{anonymous_id}/update-info",tags=["User"])
def update_user_info(anonymous_id: str, user_data: UserInfoUpdate, tenant_id: int = Depends(get_current_tenant_id)):
    """Lưu thông tin người dùng trực tiếp"""
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    try:
        user = get_or_create_user_by_anonymous_id(db, anonymous_id, tenant_id)
        
        update_dict = {
            'name': user_data.name,
            'email': user_data.email,
            'phone': user_data.phone,
            'address': user_data.address
        }
        
        print(f" Lưu thông tin user {user.id}: {update_dict}")
        update_user_profile_from_message(db, user, update_dict)
        db.refresh(user)
        
        return {
            "status": "success",
            "user_id": user.id,
            "message": "Thông tin đã được lưu"
        }
    except Exception as e:
        print(f" Lỗi lưu thông tin: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

@router.get("/users", tags=["User"])
def list_users(tenant_id: int = Depends(get_current_tenant_id)):
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    try:
        users = get_all_users(db, tenant_id)
        
        # Format users as JSON objects with all fields
        formatted_users = []
        for user in users:
            # Lấy last message của user từ conversation của tenant này
            last_message = ""
            conversation_id = None
            try:
                from models.conversation import Conversation
                conversation = db.query(Conversation).filter(
                    Conversation.user_id == user.id,
                    Conversation.tenant_id == tenant_id
                ).first()
                
                if conversation:
                    conversation_id = conversation.id
                    last_msg = db.query(Message).filter(
                        Message.conversation_id == conversation.id
                    ).order_by(desc(Message.created_at)).first()
                    
                    if last_msg:
                        last_message = last_msg.content[:50] if len(last_msg.content) > 50 else last_msg.content
            except Exception as e:
                print(f"Error getting last message for user {user.id}: {e}")
                last_message = ""
            
            formatted_users.append({
                "id": user.id,
                "name": user.full_name or "N/A",
                "email": user.email or "N/A",
                "phone": user.phone or "N/A",
                "address": user.address or "N/A",
                "anonymous_id": user.anonymous_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_message": last_message,
                "conversation_id": conversation_id,
                "disable_bot_response": conversation.disable_bot_response if conversation else False
            })
        
        return formatted_users
    finally:
        db.close()


@router.delete("/users/{user_id}", tags=["User"])
def delete_user(user_id: int, tenant_id: int = Depends(get_current_tenant_id)):
    """Xóa user và tất cả conversation, message liên quan"""
    # 🔐 Import RLS helper
    from db.session import set_tenant_context
    
    db = SessionLocal()
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    try:
        result = delete_user_with_cascading(db, user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f" Lỗi xóa user: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
