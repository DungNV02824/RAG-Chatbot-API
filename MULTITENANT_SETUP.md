# 🚀 Multi-Tenant Implementation Guide

Hệ thống đã được cập nhật để hỗ trợ multi-tenant. Dưới đây là các bước thực hiện:

## 📋 Điều đã thay đổi

### 1️⃣ Models (Database Schema)

#### ✅ Tạo bảng `tenants`
- File: `models/tenant.py`
- Bảng lưu thông tin các web/chatbot
- Trường: `id`, `name`, `description`, `api_key`, `is_active`, `created_at`, `updated_at`

#### ✅ Cập nhật bảng `documents`
- Thêm `tenant_id` (Foreign Key → tenants.id)
- Mỗi document thuộc về 1 tenant cụ thể

#### ✅ Cập nhật bảng `conversations`
- Thêm `tenant_id` (Foreign Key → tenants.id)
- Mỗi conversation thuộc về 1 tenant cụ thể

### 2️⃣ Services

#### ✅ RAG Service (`service/rag.py`)
- `retrieve_context()` giờ nhận `tenant_id` để filter documents
- Chỉ truy xuất dữ liệu của tenant đó

#### ✅ Conversation Service (`service/conversation_service.py`)
- `get_or_create_conversation()` giờ nhận `tenant_id`
- Filter conversations theo tenant_id + user_id

### 3️⃣ API Endpoints

#### ✅ Chat API (`api/chat.py`)
- `/chat` - Nhận `tenant_id` trong request body
- `/chat/history/{tenant_id}/{anonymous_id}` - Filter theo tenant_id
- `/chat/conversation/{tenant_id}/{conversation_id}` - Filter theo tenant_id
- `/staff/escalations/{tenant_id}` - Lấy escalations của tenant
- `/staff/escalation/{tenant_id}/{escalation_id}` - Chi tiết escalation của tenant
- `/staff/reply/{tenant_id}/{escalation_id}` - Trả lời escalation
- `/staff/escalation/{tenant_id}/{escalation_id}/resolve` - Resolve escalation
- `/staff/escalation/{tenant_id}/{escalation_id}/assign` - Gán escalation
- `/chat/conversation/{tenant_id}/{conversation_id}/disable-bot` - Tắt bot response

#### ✅ Ingest API (`api/ingest.py`)
- `/upload-excel?tenant_id=<id>` - Upload excel documents cho tenant

#### ✅ User API (`api/list_user.py`)
- `/users/{tenant_id}` - Lấy users và conversations của tenant

## 🔧 Database Migration

### Step 1: Tạo bảng tenants

```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description VARCHAR(500),
    api_key VARCHAR(255) UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Step 2: Thêm tenant_id vào documents

```sql
ALTER TABLE documents ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE documents ADD CONSTRAINT fk_documents_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id);
CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
```

### Step 3: Thêm tenant_id vào conversations

```sql
ALTER TABLE conversations ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE conversations ADD CONSTRAINT fk_conversations_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id);
CREATE INDEX idx_conversations_tenant_id ON conversations(tenant_id);
```

### Step 4: Tạo tenants mẫu

```sql
INSERT INTO tenants (name, description, api_key) VALUES 
('chatbot-web-1', 'Web bán hàng #1', 'key-web-1-abc123'),
('chatbot-web-2', 'Web bán hàng #2', 'key-web-2-def456'),
('chatbot-support', 'Support chatbot', 'key-support-ghi789');
```

## 📝 Cách sử dụng API

### 1. Chat API

```json
POST /chat
{
  "tenant_id": 1,
  "message": "Hỏi gì đó",
  "anonymous_id": "user123",
  "name": "Tên khách",
  "email": "email@example.com",
  "phone": "0123456789",
  "address": "Địa chỉ"
}
```

### 2. Upload Excel (Ingest)

```bash
curl -X POST "http://localhost:8000/upload-excel?tenant_id=1" \
  -F "file=@products.xlsx"
```

### 3. Lấy lịch sử chat

```bash
curl "http://localhost:8000/chat/history/1/user123"
```

### 4. Lấy danh sách escalations

```bash
curl "http://localhost:8000/staff/escalations/1?status=pending"
```

### 5. Trả lời escalation

```json
POST /staff/reply/1/123
{
  "tenant_id": 1,
  "message": "Phản hồi của nhân viên",
  "staff_name": "Nhân viên A"
}
```

## 🔒 Security Best Practices

### 1. Validate Tenant Access
- Luôn filter theo `tenant_id` khi query database
- Không cho phép user của tenant A truy cập dữ liệu tenant B

### 2. API Key Authentication (Optional)
- Có thể thêm middleware kiểm tra `api_key` từ request header
- Mỗi tenant có 1 API key duy nhất

### 3. Isolation
- Dữ liệu của mỗi tenant hoàn toàn tách biệt
- Không trộn dữ liệu giữa các tenant

## 📊 Architecture

```
1 API Server
    ↓
┌─────────────────────────────────────┐
│         FastAPI Backend             │
│  • Single instance (port 8000)      │
│  • Multi-tenant logic               │
└─────────────────────────────────────┘
    │       │       │
    ↓       ↓       ↓
┌──────┬──────┬──────┐
│ Web1 │ Web2 │ Web3 │  (Multiple Frontend)
│Chat1 │Chat2 │Chat3 │  (Each is a chatbot)
└──────┴──────┴──────┘
    ↓       ↓       ↓
Database (Shared, but data isolated by tenant_id)
```

## ✅ Checklist

- [x] Tạo model Tenant
- [x] Thêm tenant_id vào Document
- [x] Thêm tenant_id vào Conversation
- [x] Filter RAG queries theo tenant_id
- [x] Cập nhật tất cả API endpoints
- [ ] Chạy database migrations
- [ ] Tạo tenants trong database
- [ ] Test với curl hoặc Postman
- [ ] Cập nhật Frontend để gửi tenant_id

## 🧪 Testing

### Test với curl

```bash
# 1. Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "message": "Xin chào",
    "anonymous_id": "test123"
  }'

# 2. Upload Excel
curl -F "tenant_id=1" -F "file=@test.xlsx" http://localhost:8000/upload-excel

# 3. Get users
curl http://localhost:8000/users/1

# 4. Get escalations
curl http://localhost:8000/staff/escalations/1
```

## 📚 References

- Các model được cập nhật: `BE/models/`
- API endpoints: `BE/api/`
- Services: `BE/service/`
- Database: Sử dụng PostgreSQL với pgvector
