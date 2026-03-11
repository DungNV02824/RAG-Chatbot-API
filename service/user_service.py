import re
from db.session import SessionLocal
from sqlalchemy.orm import Session
from models.user import User

# 1. Tách thông tin từ câu chat
def extract_user_info(message: str) -> dict:
    info = {}
    
    # Chuẩn hóa: loại bỏ dấu tiếng Việt và chuyển về chữ thường để dễ xử lý
    message_lower = message.lower()
    
    # 1. Phone (VN) - nhiều định dạng
    phone_patterns = [
        r"(0\d{9})",  # 0909123456
        r"(\(\+84\)\s?\d{9})",  # (+84) 909123456
        r"(\+84\s?\d{9})",  # +84 909123456
    ]
    
    for pattern in phone_patterns:
        phone_match = re.search(pattern, message)
        if phone_match:
            # Chuẩn hóa số điện thoại: chỉ lấy số, bỏ ký tự đặc biệt
            phone = re.sub(r'\D', '', phone_match.group(1))
            if phone.startswith('84') and len(phone) == 11:
                phone = '0' + phone[2:]  # +84909123456 -> 0909123456
            info["phone"] = phone
            break

    # 2. Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', message, re.IGNORECASE)
    if email_match:
        info["email"] = email_match.group().lower()

    # 3. Họ tên - nhiều trường hợp
    full_name = None
    
    # Trường hợp 1: Có từ "tên" trong câu
    if "tên" in message_lower:
        # Tìm phần sau từ "tên"
        name_match = re.search(r'tên\s*(?:là|là\s+)?([^,.!?]+)', message_lower)
        if name_match:
            full_name = name_match.group(1).strip().title()
    
    # Trường hợp 2: Có từ "họ tên" trong câu
    elif "họ tên" in message_lower:
        name_match = re.search(r'họ\s*tên\s*(?:là|là\s+)?([^,.!?]+)', message_lower)
        if name_match:
            full_name = name_match.group(1).strip().title()
    
    # Trường hợp 3: Tên đứng đầu câu (trước dấu phẩy đầu tiên)
    if not full_name:
        # Lấy phần đầu tiên trước dấu phẩy hoặc dấu chấm
        first_part = re.split(r'[,.!?]', message)[0].strip()
        # Kiểm tra xem có phải là tên không (chứa chữ cái, không chứa số)
        if re.match(r'^[^\d]*$', first_part) and len(first_part.split()) >= 2:
            full_name = first_part.title()
    
    if full_name:
        info["full_name"] = full_name

    # 4. Địa chỉ - nhiều trường hợp
    address = None
    
    # Trường hợp 1: Có từ "ở", "địa chỉ", "đc"
    address_keywords = ['ở', 'địa chỉ', 'đc', 'address']
    for keyword in address_keywords:
        if keyword in message_lower:
            # Tìm phần sau từ khóa địa chỉ
            addr_match = re.search(fr'{keyword}\s*(?:là|là\s+)?([^,.!?]+)', message_lower)
            if addr_match:
                address = addr_match.group(1).strip().title()
                break
    
    # Trường hợp 2: Địa chỉ cuối câu (sau dấu phẩy cuối cùng)
    if not address:
        parts = re.split(r'[,.!?]', message)
        if len(parts) > 1:
            last_part = parts[-1].strip()
            # Kiểm tra nếu phần cuối có vẻ là địa chỉ
            if any(keyword in last_part.lower() for keyword in ['hà nội', 'hcm', 'tp', 'thành phố', 'quận', 'huyện']):
                address = last_part.title()
            elif len(last_part) > 3 and not re.search(r'\d', last_part):
                address = last_part.title()
    
    if address:
        info["address"] = address

    return info


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



# def get_or_create_user_by_anonymous_id(db, anonymous_id: str):
#     if not anonymous_id:
#         raise ValueError("anonymous_id is required")

#     user = db.query(User).filter(User.anonymous_id == anonymous_id).first()
#     if user:
#         return user

#     user = User(anonymous_id=anonymous_id)
#     db.add(user)
#     db.commit()
#     db.refresh(user)
#     return user

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
        tenant_id=tenant_id   # 🔥 QUAN TRỌNG
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


