# 📄 RAG Chatbot API (FastAPI + PostgreSQL)

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
