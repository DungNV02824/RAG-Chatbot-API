ORDER_KEYWORDS = [
    "đặt hàng",
    "mua",
    "chốt đơn",
    "order",
    "đặt mua",
    "mua sản phẩm",
    "tôi muốn đặt hàng",
    "tôi muốn mua",
    "mua hàng",
    "đặt hàng giúp tôi",
    "giúp tôi đặt hàng",
    "tôi muốn chốt đơn",
    "chốt đơn giúp tôi",
    "tôi muốn order",
    "order giúp tôi",
    "tôi muốn đặt mua",
    "đặt mua giúp tôi",
]

ESCALATE_KEYWORDS = [
    "chuyển nhân viên",
    "tôi muốn nói với nhân viên",
    "cần gặp nhân viên",
    "chuyển sang người thật",
    "người thật",
    "support",
    "hỗ trợ",
    "giúp đỡ",
    "liên hệ",
    "tư vấn viên",
    "tư vấn",
    "gặp nhân viên",
    "nói chuyện với nhân viên",
    " tôi muốn gặp nhân viên",
    "kết nối với nhân viên"

]

def is_order_intent(message: str) -> bool:
    msg = message.lower()
    return any(k in msg for k in ORDER_KEYWORDS)

def is_escalate_intent(message: str) -> bool:
    """Detect khi user muốn chuyển sang nhân viên thực"""
    msg = message.lower()
    return any(k in msg for k in ESCALATE_KEYWORDS)

