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
    db = SessionLocal()
    try:
        users = db.query(User)\
            .filter(User.tenant_id == tenant_id)\
            .order_by(User.id.asc())\
            .all()

        return users
    finally:
        db.close()


