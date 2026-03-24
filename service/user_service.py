import re
from db.session import SessionLocal
from sqlalchemy.orm import Session
from models.user import User

import re

def update_user_profile_from_message(db, user, info):
    """
    Cập nhật thông tin user từ dict info hoặc từ message string
    
    Args:
        db: Database session
        user: User object
        info: Dict với keys {name, email, address, phone} hoặc string message
    """
    if not user:
        return
    
    # Nếu info là dict (từ form/request)
    if isinstance(info, dict):
        # Chỉ cập nhật nếu giá trị không rỗng
        name_value = info.get('name')
        if name_value and isinstance(name_value, str) and name_value.strip() and name_value.strip().lower() != 'string':
            user.full_name = name_value.strip()
            print(f"  📝 full_name: {name_value.strip()}")
        
        phone_value = info.get('phone')
        if phone_value and isinstance(phone_value, str) and phone_value.strip() and phone_value.strip().lower() != 'string':
            # Check if phone already exists for a different user
            existing_user = db.query(User).filter(
                User.phone == phone_value.strip(),
                User.id != user.id
            ).first()
            
            if existing_user:
                print(f"  ⚠️ SĐT {phone_value.strip()} đã được sử dụng bởi user khác, bỏ qua update")
            else:
                user.phone = phone_value.strip()
                print(f"  📞 phone: {phone_value.strip()}")
        
        email_value = info.get('email')
        if email_value and isinstance(email_value, str) and email_value.strip() and email_value.strip().lower() != 'string':
            # Check if email already exists for a different user
            existing_user = db.query(User).filter(
                User.email == email_value.strip(),
                User.id != user.id
            ).first()
            
            if existing_user:
                print(f"  ⚠️ Email {email_value.strip()} đã được sử dụng bởi user khác, bỏ qua update")
            else:
                user.email = email_value.strip()
                print(f"  📧 email: {email_value.strip()}")
        
        address_value = info.get('address')
        if address_value and isinstance(address_value, str) and address_value.strip() and address_value.strip().lower() != 'string':
            user.address = address_value.strip()
            print(f"  🏠 address: {address_value.strip()}")
    
    # Nếu info là string (từ chat message)
    elif isinstance(info, str):
        message = info
        
        # Phone
        phone_match = re.search(r"(0\d{9,10})", message)
        if phone_match:
            phone_value = phone_match.group(1)
            # Check if phone already exists for a different user
            existing_user = db.query(User).filter(
                User.phone == phone_value,
                User.id != user.id
            ).first()
            
            if not existing_user:
                user.phone = phone_value

        # Name
        if "tên" in message.lower() and not user.full_name:
            user.full_name = message.replace("tên", "").strip()

        # Address
        if any(k in message.lower() for k in ["địa chỉ", "ở", "sống tại"]):
            user.address = message.strip()

    db.commit()
    print(f"  ✅ Database committed!")

def get_or_create_user_by_anonymous_id(db, anonymous_id: str, tenant_id: int):
    if not anonymous_id:
        raise ValueError("anonymous_id is required")

    user = db.query(User).filter(
        User.anonymous_id == anonymous_id,
        User.tenant_id == tenant_id
    ).first()

    if user:
        return user

    user = User(
        anonymous_id=anonymous_id,
        tenant_id=tenant_id  
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_all_users(db, tenant_id: int):
    """
    List users for a tenant.

    Note: Must use the provided SQLAlchemy session so the caller can set
    PostgreSQL RLS context on the same connection.
    """
    users = db.query(User)\
        .filter(User.tenant_id == tenant_id)\
        .order_by(User.id.asc())\
        .all()

    return users


def delete_user_with_cascading(db: Session, user_id: int, tenant_id: int):
    """
    Xóa user và tất cả Conversation, Message, Escalation liên quan
    
    Args:
        db: Database session
        user_id: ID của user cần xóa
        tenant_id: ID của tenant (để verify ownership)
    
    Returns:
        Message thành công hoặc raise exception
    """
    from models.conversation import Conversation
    from models.message import Message
    from models.escalation import Escalation
    
    # Lấy user và kiểm tra ownership
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant_id
    ).first()
    
    if not user:
        raise ValueError(f"User {user_id} không tồn tại hoặc không thuộc tenant {tenant_id}")
    
    # Lấy tất cả conversations của user
    conversations = db.query(Conversation).filter(
        Conversation.user_id == user_id
    ).all()
    
    # Xóa tất cả escalations liên quan đến conversations của user
    for conversation in conversations:
        db.query(Escalation).filter(
            Escalation.conversation_id == conversation.id
        ).delete()
        print(f"  🗑️ Xóa tất cả escalations trong conversation {conversation.id}")
    
    # Xóa tất cả messages trong các conversations
    for conversation in conversations:
        db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).delete()
        print(f"  🗑️ Xóa tất cả messages trong conversation {conversation.id}")
    
    # Xóa tất cả conversations của user
    db.query(Conversation).filter(
        Conversation.user_id == user_id
    ).delete()
    print(f"  🗑️ Xóa tất cả conversations của user {user_id}")
    
    # Xóa user
    db.delete(user)
    db.commit()
    print(f"  ✅ Xóa user {user_id} thành công!")
    
    return {"status": "success", "message": f"User {user_id} và tất cả dữ liệu liên quan đã bị xóa"}


