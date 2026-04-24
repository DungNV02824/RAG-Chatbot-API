from typing import Dict, List

from fastapi import WebSocket

# Danh sách kết nối WebSocket theo conversation_id
conversation_connections: Dict[int, List[WebSocket]] = {}

# 1. HÀM GỬI TIN NHẮN (Đã bọc ép kiểu String và thêm Log)
async def broadcast_staff_message(conversation_id, payload: dict) -> None:
    # BẮT BUỘC ép thành string để tránh lỗi 7 và "7"
    cid_str = str(conversation_id) 
    
    print(f"\n🔥 [DEBUG WS] Bắt đầu gọi hàm broadcast_staff_message")
    print(f"   👉 Phòng cần gửi đến: '{cid_str}'")
    print(f"   👉 Các phòng ĐANG CÓ NGƯỜI: {list(conversation_connections.keys())}")
    
    connections = conversation_connections.get(cid_str, [])
    
    if not connections:
        print(f"❌ [LỖI WS] Không tìm thấy ai đang kết nối ở phòng '{cid_str}'. Hủy gửi!\n")
        return

    print(f"✅ [OK WS] Tìm thấy {len(connections)} thiết bị trong phòng '{cid_str}'. Bắt đầu bắn tin nhắn...")
    
    disconnected = []
    for ws in connections:
        try:
            await ws.send_json(payload)
            print("   🟢 Đã gửi thành công JSON qua WebSocket!")
        except Exception as e:
            print(f"   🔴 Lỗi kết nối WS bị đứt: {e}")
            disconnected.append(ws)

    # Dọn rác
    for ws in disconnected:
        if ws in connections:
            connections.remove(ws)
    if not connections:
        conversation_connections.pop(cid_str, None)