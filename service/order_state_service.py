import re

from service.order_validator import is_valid_username, is_valid_address, is_valid_email, extract_phone_number, extract_email, extract_quantity, extract_username

def update_user_by_order_step(db, user, conversation, message: str):
    """
    Cập nhật thông tin người dùng dựa trên bước đặt hàng hiện tại
    """
    if not conversation or not conversation.order_step:
        return False

    step = conversation.order_step
    message = message.strip()

    if step == "ASK_NAME":
        # Lưu trực tiếp tên mà user nhập (chỉ loại bỏ ký tự đặc biệt)
        message = message.strip()
        
        # Loại bỏ ký tự đặc biệt (giữ lại chữ cái, số, khoảng trắng, dấu gạch ngang)
        cleaned_name = re.sub(r'[<>{}[\]\\|^`"!@#$%&*()=+~;:/?,.]', '', message).strip()
        
        if len(cleaned_name) >= 2 and len(cleaned_name) <= 100:
            user.full_name = cleaned_name
        else:
            return False

    elif step == "ASK_PHONE":
        # Sử dụng hàm extract_phone_number để trích xuất số điện thoại
        phone = extract_phone_number(message)
        if phone:
            user.phone = phone
        else:
            # Thử cách cũ nếu hàm mới không tìm thấy
            phone_match = re.search(r"(0\d{9,10})", message)
            if phone_match:
                user.phone = phone_match.group(1)
            else:
                return False

    elif step == "ASK_ADDRESS":
        # Kiểm tra địa chỉ hợp lệ
        if is_valid_address(message):
            user.address = message.strip()
        else:
            # Nếu địa chỉ quá ngắn, có thể yêu cầu nhập lại hoặc lưu tạm
            if len(message) > 5:  # Chấp nhận địa chỉ ngắn nhưng có ý nghĩa
                user.address = message.strip()
            else:
                return False

    elif step == "ASK_EMAIL":
        # Kiểm tra email hợp lệ
        email = extract_email(message)
        if email:
            user.email = email
        else:
            return False

    elif step == "ASK_QTY":
        # Xử lý số lượng (nếu cần lưu vào user hoặc order)
        # Thường số lượng sẽ được lưu vào đơn hàng, nhưng có thể lưu tạm vào user
        qty = extract_quantity(message)
        if qty and qty > 0:
            # Lưu vào user hoặc conversation tùy vào thiết kế database
            # Ví dụ: user.temp_quantity = qty
            # Hoặc: conversation.temp_quantity = qty
            pass
        else:
            return False

    elif step == "ASK_NOTE":
        # Xử lý ghi chú
        if len(message) > 0:
            # Lưu ghi chú vào conversation hoặc order
            # Ví dụ: conversation.temp_note = message
            pass
        else:
            return False

    try:
        db.commit()
        db.refresh(user)  # Reload user để verify dữ liệu đã lưu
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi khi cập nhật thông tin người dùng ở step {step}: {e}")
        print(f"Message: {message}")
        print(f"User data - name: {user.full_name}, phone: {user.phone}, email: {user.email}")
        return False