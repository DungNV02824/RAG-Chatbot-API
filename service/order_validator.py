import re
from typing import Optional, List, Tuple

def extract_phone_number(message: str) -> Optional[str]:
    """
    Trích xuất số điện thoại từ message
    Hỗ trợ các định dạng: 0912345678, 0912 345 678, 0912-345-678, 84-912345678
    """
    # Xóa tất cả ký tự không phải số và dấu +
    cleaned = re.sub(r'[^\d+]', '', message)
    
    # Tìm các chuỗi số có độ dài 9-11
    matches = re.findall(r'\d{9,11}', cleaned)
    if matches:
        return matches[0]
    
    # Thử tìm số có 12 chữ số (có thể bao gồm mã quốc gia)
    matches = re.findall(r'\d{12,15}', cleaned)
    if matches:
        # Cắt bớt để lấy 9-11 chữ số cuối
        number = matches[0]
        if len(number) > 11:
            number = number[-11:]  # lấy 11 chữ số cuối
        if 9 <= len(number) <= 11:
            return number
    
    return None

def extract_quantity(message: str) -> Optional[int]:
    """
    Trích xuất số lượng từ message
    """
    # Tìm các số trong message
    matches = re.findall(r'\b(\d+)\b', message.lower())
    
    if matches:
        # Ưu tiên số đứng riêng hoặc sau từ khóa số lượng
        for i, match in enumerate(matches):
            idx = message.find(match)
            if idx > 0:
                # Kiểm tra xem có từ khóa số lượng trước đó không
                prev_text = message[max(0, idx-20):idx].lower()
                if any(keyword in prev_text for keyword in 
                      ['số lượng', 'số', 'sl', 'quantity', 'qty', 'cần', 'muốn', 'đặt']):
                    try:
                        return int(match)
                    except ValueError:
                        continue
            
        # Nếu không tìm thấy theo ngữ cảnh, lấy số đầu tiên
        try:
            return int(matches[0])
        except ValueError:
            pass
    
    # Kiểm tra số bằng chữ (một, hai, ba...)
    word_to_number = {
        'một': 1, 'hai': 2, 'ba': 3, 'bốn': 4, 'năm': 5,
        'sáu': 6, 'bảy': 7, 'tám': 8, 'chín': 9, 'mười': 10
    }
    
    words = message.lower().split()
    for i, word in enumerate(words):
        if word in word_to_number:
            return word_to_number[word]
    
    return None

def is_valid_address(message: str) -> bool:
    """
    Kiểm tra địa chỉ hợp lệ
    """
    # Loại bỏ các từ dừng (stop words)
    stop_words = {'tôi', 'muốn', 'đặt', 'hàng', 'giao', 'tới', 'tại', 'địa', 'chỉ', 'ở', 'cho'}
    words = [word for word in re.findall(r'\b\w{2,}\b', message.lower()) 
             if word not in stop_words and not word.isdigit()]
    
    # Địa chỉ hợp lệ nếu có ít nhất 3 từ có nghĩa
    if len(words) < 3:
        return False
    
    # Kiểm tra xem có chứa từ khóa địa chỉ không
    address_keywords = {'số', 'đường', 'phố', 'phường', 'quận', 'huyện', 'tỉnh', 'thành phố', 
                       'tp', 'xã', 'ấp', 'thôn', 'làng', 'khu', 'tòa', 'chung cư', 'apartment'}
    
    has_address_keyword = any(keyword in message.lower() for keyword in address_keywords)
    
    # Hoặc có số nhà + tên đường
    has_house_number = bool(re.search(r'\b(số\s*\d+|\d+\s*[/-]\s*\d+)\b', message.lower()))
    
    return (has_address_keyword or has_house_number) and len(message) > 15

def is_valid_username(message: str) -> bool:
    """
    Kiểm tra tên người dùng hợp lệ - RELAX VALIDATION
    """
    message = message.strip()

    if len(message) < 2 or len(message) > 100:
        return False

    # Loại bỏ các ký tự đặc biệt cực kì lạ
    # Cho phép: chữ cái, số, khoảng trắng, dấu chấm, gạch ngang, dấu gạch dưới
    if not re.match(r'^[A-Za-zÀ-ỹ0-9\s\.\-_]+$', message):
        return False

    words = message.split()

    # Phải có ít nhất 1 từ (không phải chỉ toàn số hoặc ký hiệu)
    text_words = [w for w in words if any(c.isalpha() for c in w)]
    if len(text_words) == 0:
        return False

    return True

def extract_username(message: str) -> Optional[str]:
    """
    Trích xuất tên người dùng từ message
    Nếu không valid, lưu trực tiếp sau khi clean
    """
    message = message.strip()
    
    if is_valid_username(message):
        # Chuẩn hóa tên: viết hoa chữ cái đầu mỗi từ
        words = message.split()
        capitalized_words = []
        for word in words:
            if word:
                # Capitalize từng từ, giữ lại số và ký tự khác
                capitalized_words.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
        
        return ' '.join(capitalized_words)
    
    # Nếu không valid, cố gắng clean & lưu
    cleaned = re.sub(r'[<>{}[\]\\|^`"\'!@#$%&*()=+~;:/?,]', '', message).strip()
    if len(cleaned) >= 2:
        words = cleaned.split()
        result = []
        for word in words:
            if len(word) >= 1 and word:
                result.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
        return ' '.join(result) if result else None
    
    return None

def is_valid_email(message: str) -> bool:
    """
    Kiểm tra email hợp lệ
    """
    message = message.strip().lower()
    
    # Regex pattern cho email cơ bản
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # Kiểm tra pattern cơ bản
    if not re.match(email_pattern, message):
        return False
    
    # Kiểm tra độ dài
    if len(message) < 6 or len(message) > 254:
        return False
    
    # Kiểm tra các phần của email
    parts = message.split('@')
    if len(parts) != 2:
        return False
    
    local_part, domain_part = parts
    
    # Kiểm tra local part
    if len(local_part) < 1 or len(local_part) > 64:
        return False
    
    # Kiểm tra domain part
    if len(domain_part) < 4 or len(domain_part) > 255:
        return False
    
    # Kiểm tra domain có ít nhất một dấu chấm
    if '.' not in domain_part:
        return False
    
    # Kiểm tra không có hai dấu chấm liên tiếp
    if '..' in message:
        return False
    
    # Kiểm tra không bắt đầu hoặc kết thúc bằng dấu chấm
    if message.startswith('.') or message.endswith('.'):
        return False
    
    # Kiểm tra domain extension hợp lệ
    domain_parts = domain_part.split('.')
    if len(domain_parts) < 2:
        return False
    
    extension = domain_parts[-1]
    valid_extensions = {'com', 'vn', 'org', 'net', 'edu', 'gov', 'info', 'biz', 
                       'io', 'co', 'uk', 'us', 'ca', 'au', 'jp', 'kr', 'cn'}
    
    # Chấp nhận tất cả extensions có ít nhất 2 ký tự
    if len(extension) < 2:
        return False
    
    # (Tùy chọn) có thể kiểm tra extension cụ thể
    # if extension not in valid_extensions:
    #     return False
    
    return True

def extract_email(message: str) -> Optional[str]:
    """
    Trích xuất email từ message
    """
    message = message.strip()
    
    # Tìm tất cả các chuỗi có thể là email
    email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
    matches = re.findall(email_pattern, message)
    
    for match in matches:
        if is_valid_email(match):
            return match.lower()  # Trả về email viết thường
    
    # Nếu không tìm thấy bằng regex, kiểm tra toàn bộ message
    if is_valid_email(message):
        return message.lower()
    
    return None

def is_answer_for_order_step(step: str, message: str) -> bool:
    """
    Kiểm tra message có phải là câu trả lời hợp lệ cho bước đặt hàng không
    """
    message = message.strip()
    
    if len(message) == 0:
        return False
    
    if step == "ASK_PHONE":
        phone = extract_phone_number(message)
        return phone is not None
    
    elif step == "ASK_ADDRESS":
        return is_valid_address(message)
    
    elif step == "ASK_QTY":
        qty = extract_quantity(message)
        return qty is not None and qty > 0
    
    elif step == "ASK_NOTE":
        # Loại bỏ các câu trả lời quá ngắn hoặc không có ý nghĩa
        # Giữ lại các ghi chú có ít nhất 3 ký tự thực sự
        cleaned = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', message)).strip()
        words = cleaned.split()
        
        # Nếu chỉ có 1 từ, kiểm tra độ dài
        if len(words) == 1:
            return len(words[0]) >= 3
        # Nếu có nhiều từ, chấp nhận
        return len(words) > 0
    
    elif step == "ASK_NAME":
        # Kiểm tra tên: tối thiểu 2 ký tự, tối đa 100 ký tự
        return len(message.strip()) >= 2 and len(message.strip()) <= 100
    
    elif step == "ASK_EMAIL":
        return is_valid_email(message)
    
    return False


# Hàm tiện ích để lấy giá trị đã trích xuất
def extract_value_for_step(step: str, message: str):
    """
    Trích xuất giá trị từ message cho từng bước
    """
    if step == "ASK_PHONE":
        return extract_phone_number(message)
    elif step == "ASK_QTY":
        return extract_quantity(message)
    elif step == "ASK_ADDRESS":
        return message.strip() if is_valid_address(message) else None
    elif step == "ASK_NOTE":
        return message.strip()
    elif step == "ASK_NAME":
        return extract_username(message)
    elif step == "ASK_EMAIL":
        return extract_email(message)
    return None


# Hàm kiểm tra tổng hợp cho tất cả các bước
def validate_all_steps(order_data: dict) -> dict:
    """
    Kiểm tra tính hợp lệ của tất cả dữ liệu đơn hàng
    Trả về dict chứa kết quả kiểm tra và thông báo lỗi nếu có
    """
    result = {
        'is_valid': True,
        'errors': [],
        'validated_data': {}
    }
    
    # Kiểm tra từng trường
    if 'username' in order_data:
        if is_valid_username(order_data['username']):
            result['validated_data']['username'] = extract_username(order_data['username'])
        else:
            result['is_valid'] = False
            result['errors'].append('Tên không hợp lệ. Vui lòng nhập tên đầy đủ của bạn.')
    
    if 'phone' in order_data:
        phone = extract_phone_number(order_data['phone'])
        if phone:
            result['validated_data']['phone'] = phone
        else:
            result['is_valid'] = False
            result['errors'].append('Số điện thoại không hợp lệ.')
    
    if 'email' in order_data:
        email = extract_email(order_data['email'])
        if email:
            result['validated_data']['email'] = email
        else:
            result['is_valid'] = False
            result['errors'].append('Email không hợp lệ.')
    
    if 'address' in order_data:
        if is_valid_address(order_data['address']):
            result['validated_data']['address'] = order_data['address'].strip()
        else:
            result['is_valid'] = False
            result['errors'].append('Địa chỉ không đầy đủ. Vui lòng cung cấp địa chỉ chi tiết hơn.')
    
    if 'quantity' in order_data:
        qty = extract_quantity(str(order_data['quantity']))
        if qty and qty > 0:
            result['validated_data']['quantity'] = qty
        else:
            result['is_valid'] = False
            result['errors'].append('Số lượng không hợp lệ.')
    
    if 'note' in order_data:
        result['validated_data']['note'] = order_data['note'].strip() if order_data['note'] else ''
    
    return result