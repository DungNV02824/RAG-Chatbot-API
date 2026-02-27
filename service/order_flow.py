FIELD_FLOW = [
    ("ASK_PHONE", "phone", "Anh/chị cho em xin số điện thoại ạ?"),
    ("ASK_ADDRESS", "address", "Anh/chị cho em xin địa chỉ nhận hàng ạ?"),
    ("ASK_NAME", "full_name", "Anh/chị cho em xin họ tên được không ạ?"),
    ("ASK_EMAIL", "email", "Anh/chị cho em xin email được không ạ?"),
]


def get_next_order_step(user):
    """
    Xác định bước tiếp theo dựa trên thông tin user đã có
    """
    if not user.full_name:
        return ("ASK_NAME", "full_name", "Vui lòng cho tôi biết tên của bạn:")
    elif not user.phone:
        return ("ASK_PHONE", "phone", "Vui lòng cung cấp số điện thoại của bạn:")
    elif not user.email:
        return ("ASK_EMAIL", "email", "Vui lòng cho biết email của bạn (nếu có):")
    elif not user.address:
        return ("ASK_ADDRESS", "address", "Vui lòng cho biết địa chỉ giao hàng chi tiết:")
    else:
        # Đã có đủ thông tin cơ bản
        return None


def get_order_step_question(step: str) -> str:
    """
    Lấy câu hỏi tương ứng với order step hiện tại
    """
    ORDER_STEPS = {
        "ASK_NAME": "cho tôi biết tên của bạn?",
        "ASK_PHONE": "vui lòng cung cấp số điện thoại liên hệ ạ.",
        "ASK_ADDRESS": "cho tôi biết địa chỉ nhận hàng cụ thể được không ạ?",
        "ASK_EMAIL": "cho tôi biết email của bạn được không ạ?",
    }
    
    return ORDER_STEPS.get(step, "")