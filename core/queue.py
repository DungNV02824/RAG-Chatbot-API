import json
from typing import Any, Callable, Optional
from arq import create_pool
from arq.connections import RedisSettings
from core.config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

# Redis settings for ARQ
redis_settings = RedisSettings(
    host=REDIS_HOST,
    port=REDIS_PORT,
    database=REDIS_DB,
    password=REDIS_PASSWORD
)

# Global pool (initialized in main.py)
_pool = None


async def init_queue():
    """Initialize the task queue connection pool"""
    global _pool
    _pool = await create_pool(redis_settings)
    return _pool


async def close_queue():
    """Close the task queue connection pool"""
    global _pool
    if _pool:
        await _pool.close()


async def enqueue_task(
    func: Callable,
    *args,
    task_id: Optional[str] = None,
    **kwargs
) -> str:
    """
    Enqueue an async task.
    
    Args:
        func: Async function to execute
        *args: Positional arguments
        task_id: Optional task ID (generated if not provided)
        **kwargs: Keyword arguments
    
    Returns:
        Job ID
    """
    global _pool
    
    if not _pool:
        raise RuntimeError("Task queue not initialized. Call init_queue() first.")
    
    try:
        job = await _pool.enqueue_job(
            func,
            *args,
            **kwargs
        )
        return job.job_id
    except Exception as e:
        print(f"Error enqueueing task: {e}")
        raise


async def get_task_result(job_id: str) -> Optional[Any]:
    """Get result of a completed task"""
    global _pool
    
    if not _pool:
        raise RuntimeError("Task queue not initialized.")
    
    try:
        job = await _pool.job(job_id)
        if job:
            return job.result
        return None
    except Exception as e:
        print(f"Error getting task result: {e}")
        return None


async def get_task_status(job_id: str) -> str:
    """Get status of a task (queued, started, completed, failed)"""
    global _pool
    
    if not _pool:
        raise RuntimeError("Task queue not initialized.")
    
    try:
        job = await _pool.job(job_id)
        if not job:
            return "not_found"
        
        if job.is_finished():
            return "completed"
        elif job.is_queued():
            return "queued"
        else:
            return "running"
            
    except Exception as e:
        print(f"Error getting task status: {e}")
        return "error"


# Task functions that can be enqueued

async def embed_document_task(document_id: int, content: str, tenant_id: int):
    """
    Async task to embed a document
    (Can be called without blocking the main API)
    """
    from service.embedding import embed_text
    from db.session import SessionLocal
    from models.document import Document
    
    db = SessionLocal()
    try:
        embedding = embed_text(content)
        
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.embedding = embedding
            db.commit()
            
        print(f"Document {document_id} embedded successfully")
        return True
    except Exception as e:
        print(f"Error embedding document {document_id}: {e}")
        return False
    finally:
        db.close()


async def summarize_conversation_task(conversation_id: int, tenant_id: int):
    """
    Async task to summarize a long conversation
    """
    from db.session import SessionLocal
    from service.summarization_service import summarize_conversation
    
    db = SessionLocal()
    try:
        result = await summarize_conversation(db, conversation_id, tenant_id)
        print(f"Conversation {conversation_id} summarized successfully")
        return result
    except Exception as e:
        print(f"Error summarizing conversation {conversation_id}: {e}")
        return None
    finally:
        db.close()


async def process_ocr_task(file_path: str, tenant_id: int):
    """
    Async task to process OCR on uploaded documents
    (Heavy operation - should be done async)
    """
    try:
        # TODO: Implement OCR processing
        # from pdf2image import convert_from_path
        # from pytesseract import image_to_string
        
        print(f"Processing OCR for file: {file_path}")
        # Processing logic here
        return True
    except Exception as e:
        print(f"Error processing OCR: {e}")
        return False


async def generate_summary_task(content: str, max_tokens: int = 500) -> str:
    """
    Async task to generate summary using OpenAI
    """
    from openai import OpenAI
    from core.config import OPENAI_API_KEY, CHAT_MODEL
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là chuyên gia tóm tắt. Hãy tóm tắt nội dung sau một cách ngắn gọn nhưng đầy đủ."
                },
                {
                    "role": "user",
                    "content": f"Hãy tóm tắt nội dung sau trong {max_tokens} tokens:\n\n{content}"
                }
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        raise
