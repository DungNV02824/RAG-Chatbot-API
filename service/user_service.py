import re
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


def update_user_profile_from_message(db: Session, user: User, message: str):
    data = extract_user_info(message)
    if not data:
        return user

    for key, value in data.items():
        if value and value.strip():
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


def get_or_create_user_by_anonymous_id(db, anonymous_id: str):
    if not anonymous_id:
        raise ValueError("anonymous_id is required")

    user = db.query(User).filter(User.anonymous_id == anonymous_id).first()
    if user:
        return user

    user = User(anonymous_id=anonymous_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
