"""
PayMailHook Webhook Endpoint
-----------------------------
PayMailHook nhận email thông báo từ ngân hàng, parse ra thông tin giao dịch,
rồi POST về endpoint này để cập nhật trạng thái đơn hàng.

Payload PayMailHook gửi về:
{
    "amount": 500000,
    "referenceCode": "TT123456",   <- prefix + conversation_id
    "secretKey": "pmh_live_xxx",   <- dùng để xác minh tenant
    "timestamp": "2024-03-20T10:30:00Z"
}
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.session import get_db, set_tenant_context
from models.tenant import Tenant
from models.conversation import Conversation
from models.message import Message

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/payment",
    tags=["Payment Webhook"]
)


# ── Payload schema ────────────────────────────────────────────────────────────

class PayMailHookPayload(BaseModel):
    amount: float
    referenceCode: str
    secretKey: str
    timestamp: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_by_secret(secret_key: str, db: Session) -> Tenant:
    """Tìm tenant theo pmh_secret_key. Raise 401 nếu không khớp."""
    tenant = db.query(Tenant).filter(
        Tenant.pmh_secret_key == secret_key,
        Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret key không hợp lệ hoặc tenant không tồn tại."
        )
    return tenant


def _parse_conversation_id(reference_code: str, prefix: str) -> int:
    """
    Tách conversation_id từ referenceCode.
    VD: prefix="TT", referenceCode="TT123456" → 123456
    """
    if not reference_code.upper().startswith(prefix.upper()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"referenceCode '{reference_code}' không khớp prefix '{prefix}' của tenant."
        )
    raw_id = reference_code[len(prefix):]
    if not raw_id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Phần ID trong referenceCode '{reference_code}' không hợp lệ."
        )
    return int(raw_id)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

def _handle_renewal(tenant, payload: "PayMailHookPayload", db: Session) -> dict:
    """
    Gia hạn subscription 30 ngày cho tenant.
    - Nếu còn hạn: cộng thêm 30 ngày từ ngày hiện tại hết hạn
    - Nếu đã hết hạn / chưa có: tính từ hôm nay
    """
    now = datetime.utcnow()
    base = tenant.subscription_expires_at if (
        tenant.subscription_expires_at and tenant.subscription_expires_at > now
    ) else now

    tenant.subscription_expires_at = base + timedelta(days=30)
    tenant.is_active = True
    db.add(tenant)
    db.commit()

    logger.info(
        "Gia hạn thành công: tenant=%s expires_at=%s amount=%s ref=%s",
        tenant.id, tenant.subscription_expires_at, payload.amount, payload.referenceCode
    )

    return {
        "status": "success",
        "message": "Gia hạn subscription thành công 30 ngày.",
        "tenant_id": tenant.id,
        "subscription_expires_at": tenant.subscription_expires_at.isoformat(),
        "amount": payload.amount,
        "referenceCode": payload.referenceCode
    }


@router.post("/webhook", status_code=status.HTTP_200_OK)
def receive_payment_webhook(
    payload: PayMailHookPayload,
    db: Session = Depends(get_db)
):
    """
    Endpoint nhận webhook từ PayMailHook.

    Luồng xử lý:
    1. Xác minh secretKey → tìm ra tenant
    2. Nếu referenceCode bắt đầu bằng "RENEW" → gia hạn subscription 30 ngày
    3. Ngược lại parse referenceCode bằng prefix → lấy conversation_id → cập nhật order_step = "paid"
    """

    # 1. Xác minh secretKey
    tenant = _get_tenant_by_secret(payload.secretKey, db)

    # Set RLS context cho các query tiếp theo (conversations, messages)
    set_tenant_context(db, tenant.id)

    # 2. Nếu là thanh toán gia hạn subscription
    if payload.referenceCode.upper().startswith("RENEW"):
        return _handle_renewal(tenant, payload, db)

    if not tenant.pmh_prefix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant chưa cấu hình Prefix mã đơn hàng."
        )

    # 2. Parse conversation_id từ referenceCode
    conversation_id = _parse_conversation_id(payload.referenceCode, tenant.pmh_prefix)

    # 3. Tìm conversation
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant.id
    ).first()

    if not conversation:
        logger.warning(
            "Webhook PayMailHook: conversation %s không tìm thấy cho tenant %s",
            conversation_id, tenant.id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng với mã '{payload.referenceCode}'."
        )

    # 4. Cập nhật trạng thái thanh toán
    previous_step = conversation.order_step
    conversation.order_step = "paid"
    db.add(conversation)

    # 5. Thêm tin nhắn bot thông báo
    amount_formatted = f"{int(payload.amount):,}".replace(",", ".")
    bot_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=(
            f"✅ Xác nhận thanh toán thành công!\n"
            f"• Số tiền: {amount_formatted} VNĐ\n"
            f"• Mã giao dịch: {payload.referenceCode}\n"
            f"• Thời gian: {payload.timestamp}\n\n"
            f"Cảm ơn bạn đã thanh toán. Đơn hàng của bạn đang được xử lý."
        )
    )
    db.add(bot_message)
    db.commit()

    logger.info(
        "Thanh toán thành công: tenant=%s conversation=%s amount=%s ref=%s (order_step: %s → paid)",
        tenant.id, conversation_id, payload.amount, payload.referenceCode, previous_step
    )

    return {
        "status": "success",
        "message": "Đã cập nhật trạng thái thanh toán.",
        "conversation_id": conversation_id,
        "amount": payload.amount,
        "referenceCode": payload.referenceCode
    }
