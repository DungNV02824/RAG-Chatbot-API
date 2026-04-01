from typing import Dict, List

from fastapi import WebSocket

# Danh sách kết nối WebSocket theo conversation_id
conversation_connections: Dict[int, List[WebSocket]] = {}


async def broadcast_staff_message(conversation_id: int, payload: dict) -> None:
    """
    Gửi tin nhắn của nhân viên tới tất cả WebSocket client
    đang subscribe conversation này (phía user).
    """
    connections = conversation_connections.get(conversation_id, [])
    if not connections:
        return

    disconnected: List[WebSocket] = []

    for ws in connections:
        try:
            await ws.send_json(payload)
        except Exception:
            # Nếu WS bị ngắt thì đánh dấu để remove
            disconnected.append(ws)

    if disconnected:
        # Loại bỏ các kết nối đã chết
        alive = [ws for ws in connections if ws not in disconnected]
        if alive:
            conversation_connections[conversation_id] = alive
        else:
            conversation_connections.pop(conversation_id, None)

