# 📋 Chat Bot Flow Review & Testing Guide

## ✅ System Overview

### 1. **Chat Consultation Flow** (Tư vấn sản phẩm)
```
User nhập message → RAG tìm context từ database 
  ↓
  - Nếu mặt có ảnh → Return images
  - Nếu mặt có context → LLM trả lời dựa trên dataset
  - Nếu KHÔNG có context → Return "không tìm thấy thông tin"
```

**Bảo vệ:** LLM System Prompt bắt buộc:
- "CHỈ trả lời dựa HOÀN TOÀN trên thông tin sản phẩm"
- "KHÔNG được có bất kỳ kiến thức ngoài"
- Nếu không có → trả "em không có thông tin..." 

✅ **Status:** Sửa xong - prompt mạnh hơn

---

### 2. **Order Flow** (Đặt hàng)
```
User: "muốn đặt hàng" → is_order_intent detect
  ↓
Bot hỏi từng field: Tên → ĐT → Email → Địa chỉ
  ↓
- User validate từng field qua is_answer_for_order_step()
- Nếu invalid → yêu cầu nhập lại
- Nếu valid → lưu vào DB, hỏi field tiếp theo
  ↓
Hoàn tất đủ 4 field → "Đơn hàng được ghi nhận"
```

**Thứ tự hỏi:** 
1. ASK_NAME (Tên)
2. ASK_PHONE (ĐT) 
3. ASK_EMAIL (Email)
4. ASK_ADDRESS (Địa chỉ)

✅ **Status:** Sửa xong - xóa duplicate function

---

## 🔧 Các File Được Sửa

### 1. **api/chat.py**
- ✅ Sửa logic order flow: Bắt đầu từ `get_next_order_step()` thay vì hỏi tất cả cùng lúc
- ✅ Sửa LLM prompt: Bắt buộc chỉ trả lời từ dataset

### 2. **service/order_flow.py**
- ✅ Xóa duplicate function `get_next_order_step` (hàng cũ: return FIELD_FLOW, hàng mới: return tuple)
- ✅ Sửa `get_order_step_question()` để match với ASK_* constants

### 3. **service/order_validator.py**
- ✅ `extract_email()` đã hoàn thành
- ✅ `is_answer_for_order_step()` kiểm tra hợp lệ cho từng step
- ✅ Validation rules:
  - ASK_NAME: tối thiểu 2 ký tự, chỉ chữ cái + khoảng trắng + . - _
  - ASK_PHONE: 9-11 chữ số, hỗ trợ nhiều format
  - ASK_EMAIL: RFC-compliant email validation
  - ASK_ADDRESS: tối thiểu 15 ký tự + from address keywords

---

## 🧪 Test Cases

### Test 1: Chat Thường (Tư vấn)
```
POST /chat
{
  "message": "Bạn có sản phẩm nào?",
  "anonymous_id": "user123"
}

Expected Response:
{
  "answer": "...(trả lời từ RAG + LLM)",
  "type": "text"
}
```

### Test 2: Order Flow
```
Step 1 - User nhập order intent:
POST /chat
{
  "message": "Tôi muốn đặt hàng",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "Vui lòng cho tôi biết tên của bạn:",
  "type": "order_collect",
  "order_step": "ASK_NAME"
}

---

Step 2 - User cung cấp tên:
POST /chat
{
  "message": "Nguyễn Văn A",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "Vui lòng cung cấp số điện thoại của bạn:",
  "type": "order_collect",
  "order_step": "ASK_PHONE"
}

---

Step 3 - User cung cấp ĐT:
POST /chat
{
  "message": "0909123456",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "Vui lòng cho biết email của bạn được không ạ?",
  "type": "order_collect",
  "order_step": "ASK_EMAIL"
}

---

Step 4 - User cung cấp Email:
POST /chat
{
  "message": "user@gmail.com",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "Vui lòng cho biết địa chỉ giao hàng chi tiết:",
  "type": "order_collect",
  "order_step": "ASK_ADDRESS"
}

---

Step 5 - User cung cấp Địa chỉ:
POST /chat
{
  "message": "Số 10, đường Lê Lai, Hoàn Kiếm, Hà Nội",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "🎉 Em đã ghi nhận đầy đủ thông tin đặt hàng. Bên em sẽ liên hệ sớm để xác nhận đơn ạ!",
  "type": "order_confirm"
}

DB saved: User(id=1, name='Nguyễn Văn A', phone='0909123456', email='user@gmail.com', address='Số 10, đường Lê Lai, Hoàn Kiếm, Hà Nội')
```

### Test 3: Invalid Input (Validation Error)
```
User nhập tên không hợp lệ (quá ngắn):
POST /chat
{
  "message": "A",
  "anonymous_id": "user123"
}

Response:
{
  "answer": "Thông tin chưa hợp lệ, anh vui lòng nhập lại giúp em nhé.\n\nVui lòng cho tôi biết tên của bạn:",
  "type": "order_collect",
  "order_step": "ASK_NAME"
}
```

### Test 4: Chat Outside Dataset
```
POST /chat
{
  "message": "Viết 1 bài thơ cho tôi",
  "anonymous_id": "user123"
}

Expected: 
{
  "answer": "em không có thông tin về vấn đề này trong cơ sở dữ liệu của em...",
  "type": "text"
}
```

---

## 🔍 Kiểm Tra Cơ Bản

- [ ] Database User table có 4 field: `full_name`, `phone`, `email`, `address`
- [ ] RAG embedding hoạt động đúng (vector DB)
- [ ] OpenAI API key đã cấu hình
- [ ] CORS cho phép frontend call API
- [ ] Environment variables: OPENAI_API_KEY, CHAT_MODEL

---

## 📝 Note

- Flow order chỉ bắt đầu khi user nói "đặt hàng", "mua", "chốt đơn", v.v.
- Hỏi thông tin từng bước, KHÔNG hỏi tất cả cùng lúc
- Lưu dữ liệu vào database khi validate thành công
- LLM PHẢI chỉ trả lời từ dataset, không general knowledge
