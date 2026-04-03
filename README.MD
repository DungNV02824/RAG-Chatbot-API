# 📄 RAG Chatbot API (FastAPI + PostgreSQL/pgvector)

##  Giới thiệu
Dự án xây dựng **Chatbot hỏi đáp sử dụng RAG (Retrieval-Augmented Generation)**.  
Hệ thống cho phép:
- Upload dữ liệu (text / Excel)
- Embedding nội dung vào PostgreSQL (pgvector)
- Truy vấn ngữ nghĩa và trả lời câu hỏi qua API

---

## 🚀 Chức năng chính
- 📥 Ingest dữ liệu và lưu vector embedding
- 🔍 Truy vấn dữ liệu bằng semantic search
- 💬 Chat hỏi đáp theo ngữ cảnh
- ⚡ API xây dựng bằng FastAPI
- 🐘 PostgreSQL + pgvector lưu embedding

---

## 🛠 Công nghệ sử dụng
- **Python**
- **FastAPI**
- **PostgreSQL + pgvector**
- **SQLAlchemy**
- **SentenceTransformer / OpenAI Embedding**
- **Docker & Docker Compose**

---

## 📂 Cấu trúc thư mục
```text
TEST_SQL/
├── api/
│   ├── chat.py          # API chat hỏi đáp
│   └── ingest.py        # API ingest dữ liệu
│
├── core/
│   └── config.py        # Cấu hình hệ thống (.env)
│
├── db/
│   ├── base.py          # Khai báo Base SQLAlchemy
│   └── session.py       # Kết nối database
│
├── models/
│   └── document.py     # Model Document (content + embedding)
│
├── service/
│   ├── embedding.py    # Hàm embedding text
│   ├── embedding_ex.py # Đọc & xử lý Excel
│   └── rag.py          # Logic RAG (retrieve + generate)
│
├── env/                 # Virtual environment (local)
├── .env                 # Biến môi trường
├── docker-compose.yml   # Docker PostgreSQL + pgvector
├── main.py              # Entry point FastAPI
├── requirements.txt     # Thư viện cần cài
└── README.md
```

---
## 🚀 Cách chạy dự án (Cho người mới)

### 1) Cài Python & dependencies
```powershell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Khởi động PostgreSQL (pgvector) + Redis
```powershell
docker compose up -d
```

> Ghi chú: PostgreSQL map port `5433:5432` (vì vậy app cần trỏ sang `localhost:5433`).

### 3) Tạo file `.env`
```powershell
cp .env.example .env
```

Chỉnh ít nhất:
```env
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4
EMBEDDING_MODEL=text-embedding-3-small

DATABASE_URL=postgresql://app_user:123456@localhost:5433/chatbot_db

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### 4) Tạo schema/tables tối thiểu trong DB
Repo hiện chưa có migration/alembic, nên bạn cần tạo thủ công.

Tạo các bảng ORM:
```powershell
python -c "from db.base import Base, engine; import models.tenant, models.document, models.user, models.conversation, models.message, models.escalation; Base.metadata.create_all(bind=engine)"
```

Tạo bảng `llm_usage_logs` (được dùng trong `service/usage_service.py`):
```powershell
psql -h localhost -p 5433 -U app_user -d chatbot_db -c "
CREATE TABLE IF NOT EXISTS llm_usage_logs (
  id bigserial PRIMARY KEY,
  tenant_id integer NOT NULL,
  conversation_id integer,
  model_name text NOT NULL,
  prompt_tokens integer NOT NULL,
  completion_tokens integer NOT NULL,
  total_tokens integer NOT NULL,
  estimated_cost_usd numeric(18,6) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);"
```

Nếu máy bạn chưa cài `psql`, có thể chạy lệnh trực tiếp trong container `pgvector`:
```powershell
docker exec -i pgvector psql -U app_user -d chatbot_db -c "
CREATE TABLE IF NOT EXISTS llm_usage_logs (
  id bigserial PRIMARY KEY,
  tenant_id integer NOT NULL,
  conversation_id integer,
  model_name text NOT NULL,
  prompt_tokens integer NOT NULL,
  completion_tokens integer NOT NULL,
  total_tokens integer NOT NULL,
  estimated_cost_usd numeric(18,6) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);"
```

> Nếu gặp lỗi RLS/permission, xem các file `FIX_PERMISSIONS_ERROR.md`, `FIX_PERMISSIONS_QUICK_GUIDE.md`.

### 5) Chạy FastAPI + Worker
Terminal 1:
```powershell
uvicorn main:app --reload --port 8000
```
Terminal 2:
```powershell
python -m arq workers.WorkerSettings
```

---
## 🧭 Cách sử dụng API

### Authentication (bắt buộc header)
Hầu hết endpoint cần:
- `x-api-key: <api_key của tenant>`

Không cần `x-api-key` cho:
- `/health`, `/docs`, `/openapi.json`, `/tenants`

### 1) Tạo Tenant (lấy API key)
`POST /tenants`
```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Website A",
    "description": "Tenant demo",
    "api_key": "key-default-123"
  }'
```

### 2) Upload Excel để tạo embedding
`POST /upload-excel` (multipart/form-data)

File `.xlsx` cần cột:
- `A (Câu hỏi)`
- `B (Trả lời)`

Tùy chọn:
- `C (Key work)`
- `D(image_url)`

Ví dụ:
```powershell
curl -X POST http://localhost:8000/upload-excel `
  -H "x-api-key: key-default-123" `
  -F "file=@./data.xlsx"
```

### 3) Xóa dữ liệu tenant
`DELETE /documents/clear`
```powershell
curl -X DELETE http://localhost:8000/documents/clear -H "x-api-key: key-default-123"
```

### 4) Chat với bot
`POST /chat`

Body:
```json
{
  "message": "Nội dung câu hỏi...",
  "anonymous_id": "user1",
  "name": "optional",
  "email": "optional",
  "address": "optional",
  "phone": "optional"
}
```

Ví dụ streaming (SSE):
```bash
curl -N -X POST http://localhost:8000/chat \
  -H "x-api-key: key-default-123" \
  -H "Content-Type: application/json" \
  -d '{
    "anonymous_id": "user1",
    "message": "Sản phẩm A giá bao nhiêu?"
  }'
```

Lưu ý phản hồi:
- Thường trả về **Streaming SSE** (`event: message`, `event: done`)
- Một số trường hợp trả về **JSON thường** (ví dụ semantic cache hit, guardrail block, bot disabled)

### 5) Xem lịch sử chat (tùy chọn)
`GET /chat/history/{anonymous_id}`
```bash
curl http://localhost:8000/chat/history/user1 -H "x-api-key: key-default-123"
```

