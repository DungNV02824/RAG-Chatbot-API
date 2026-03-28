"""
Async worker queue for handling heavy tasks.
This module defines all async jobs that are executed by ARQ workers.

To run workers:
    arq workers.WorkerSettings
"""

from arq import Retry
import asyncio
import random
import sys
from models.tenant import Tenant 
from models.document import Document

# Cấu hình Retry chung
MAX_RETRIES = 5

# ========== DEFINE ASYNC JOBS ==========
# These tasks are executed asynchronously by the worker process

async def embed_document_job(ctx, document_id: int, content: str, tenant_id: int):
    from service.embedding import embed_text
    from db.session import SessionLocal, set_tenant_context
    from models.document import Document
    
    # Lấy thông tin số lần thử từ ARQ context
    job_try = ctx.get('job_try', 1)

    with SessionLocal() as db:
        try:
            print(f"🔄 [Worker] Embedding document {document_id} (Lần thử: {job_try})...")
            # set_tenant_context() gọi db_session.execute() => SQLAlchemy tự bắt đầu transaction.
            # Vì vậy phải đưa set_tenant_context() vào cùng 1 transaction scope,
            # tránh lỗi: "A transaction is already begun on this Session."
            with db.begin():
                set_tenant_context(db, tenant_id)

                # Pessimistic lock để tránh 2 worker cùng embed 1 document.
                # Giữ lock đến lúc cập nhật embedding (thread embed là IO-bound).
                doc = (
                    db.query(Document)
                    .filter(Document.id == document_id)
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if not doc:
                    print(f"⚠️ Document {document_id} đang được xử lý bởi worker khác hoặc không tồn tại. Bỏ qua.")
                    return {"success": False, "reason": "Locked or Not Found"}

                try:
                    embedding = await asyncio.to_thread(embed_text, content)
                except Exception as api_error:
                    if job_try < MAX_RETRIES:
                        defer_seconds = (2 ** job_try) + random.uniform(0, 1)
                        print(f"⚠️ Lỗi API Embedding. Thử lại sau {defer_seconds:.2f}s... (Lỗi: {api_error})")
                        raise Retry(defer=defer_seconds)
                    print(f"❌ Document {document_id} thất bại hoàn toàn sau {MAX_RETRIES} lần thử.")
                    raise api_error

                if hasattr(embedding, "tolist"):
                    embedding = embedding.tolist()
                doc.embedding = embedding

            print(f"✓ [Worker] Document {document_id} embedded successfully")
            return {"success": True}

        except Retry:
            raise # Bắt buộc phải raise lại Retry để ARQ nhận diện
        except Exception as e:
            # Với lỗi critical, nên retry để tránh worker bị crash dây chuyền (gây redis timeout).
            if job_try < MAX_RETRIES:
                defer_seconds = (2 ** job_try) + random.uniform(0, 1)
                print(f"⚠️ [Worker] Critical error in embed_document_job. Retry sau {defer_seconds:.2f}s... (Error: {e})")
                raise Retry(defer=defer_seconds)
            print(f"❌ [Worker] Critical error in embed_document_job: {e}")
            return {"success": False, "error": str(e)}


async def summarize_conversation_job(ctx, conversation_id: int, tenant_id: int):
    """Async job to summarize long conversations."""
    from service.summarization_service import summarize_conversation
    from db.session import SessionLocal
    
    job_try = ctx.get('job_try', 1)

    with SessionLocal() as db:
        try:
            print(f"🔄 [Worker] Summarizing conversation {conversation_id} (Lần thử: {job_try})...")
            
            # Hàm này gọi LLM nên cũng cần Retry Logic
            summary = await summarize_conversation(db, conversation_id, tenant_id)
            
            if summary:
                print(f"✓ [Worker] Conversation {conversation_id} summarized ({len(summary)} chars)")
                return {"success": True, "conversation_id": conversation_id, "summary_length": len(summary)}
            else:
                return {"success": False, "error": "Already summarized or too short"}
                
        except Exception as e:
            if job_try < MAX_RETRIES:
                defer_seconds = (2 ** job_try) + random.uniform(0, 1)
                print(f"⚠️ Lỗi Summarize. Thử lại sau {defer_seconds:.2f}s...")
                raise Retry(defer=defer_seconds)
            
            print(f"❌ [Worker] Error summarizing conversation {conversation_id}: {e}")
            return {"success": False, "error": str(e)}


async def process_ocr_job(ctx, file_path: str, document_id: int, tenant_id: int):
    """Async job to process OCR on PDF documents."""
    job_try = ctx.get('job_try', 1)
    
    try:
        print(f"🔄 [Worker] Processing OCR for {file_path} (Lần thử: {job_try})...")
        
        # TODO: Implement actual OCR processing
        # Ví dụ nếu gọi API AWS Textract hoặc Google Vision ở đây, nó RẤT dễ bị timeout
        
        # Giả lập xử lý nặng
        await asyncio.sleep(2) 
        
        print(f"✓ [Worker] OCR processing completed for {file_path}")
        return {"success": True, "file_path": file_path}
        
    except Exception as e:
        if job_try < MAX_RETRIES:
            defer_seconds = (2 ** job_try) + random.uniform(0, 1)
            print(f"⚠️ Lỗi OCR. Sẽ thử lại sau {defer_seconds:.2f}s...")
            raise Retry(defer=defer_seconds)
            
        print(f"❌ [Worker] Lỗi OCR sau {MAX_RETRIES} lần thử: {e}")
        return {"success": False, "error": str(e)}


async def generate_embedding_batch_job(ctx, documents: list):
    """Batch job: Retry từng phần (hoặc retry cả batch) + Database Locking"""
    from service.embedding import embed_text
    from db.session import SessionLocal
    from models.document import Document
    
    print(f"🔄 [Worker] Batch embedding {len(documents)} documents...")
    results = []

    with SessionLocal() as db:
        for doc_data in documents:
            doc_id = doc_data["id"]
            content = doc_data["content"]
            
            try:
                # Lock row để tránh Race condition
                with db.begin():
                    doc = db.query(Document).filter(Document.id == doc_id).with_for_update(skip_locked=True).first()
                    if not doc:
                        results.append({"id": doc_id, "success": False, "error": "Locked or Not found"})
                        continue
                
                # Xử lý API
                # Lưu ý: Trong thực tế batch nên gọi hàm embed batch của OpenAI thay vì lặp to_thread
                embedding = await asyncio.to_thread(embed_text, content)
                
                # Cập nhật kết quả
                with db.begin():
                    doc_update = db.query(Document).filter(Document.id == doc_id).first()
                    if doc_update:
                        if hasattr(embedding, 'tolist'):
                            embedding = embedding.tolist()
                        doc_update.embedding = embedding
                        results.append({"id": doc_id, "success": True})
                        
            except Exception as e:
                # Với batch, ta ghi nhận lỗi từng record thay vì retry cả lô lớn
                print(f"❌ Lỗi xử lý doc_id {doc_id} trong batch: {e}")
                results.append({"id": doc_id, "success": False, "error": str(e)})

        print(f"✓ [Worker] Batch embedding completed: {sum(1 for r in results if r['success'])}/{len(documents)} succeeded")
        return {"success": True, "results": results}


async def cleanup_old_cache_job(ctx, days: int = 7):
    """DB Cache Cleanup - Không cần Retry phức tạp"""
    from core.cache import redis_client
    import time
    try:
        print(f"🔄 [Worker] Cleaning up cache older than {days} days...")
        def _cleanup_sync():
            pattern = "semantic_cache:*"
            keys = redis_client.keys(pattern)
            deleted = 0
            for key in keys:
                ttl = redis_client.ttl(key)
                if ttl == -1:
                    redis_client.delete(key)
                    deleted += 1
            return {"success": True, "deleted": deleted}

        result = await asyncio.to_thread(_cleanup_sync)
        print(f"✓ [Worker] Cache cleanup completed: {result.get('deleted', 0)} keys deleted")
        return result
    except Exception as e:
        print(f"❌ [Worker] Cache cleanup error: {e}")
        return {"success": False, "error": str(e)}


async def generate_daily_stats_job(ctx):
    """Daily Stats - Sử dụng db.begin() để chỉ đọc an toàn"""
    from db.session import SessionLocal
    from models.conversation import Conversation
    from models.message import Message
    from datetime import datetime, timedelta
    
    with SessionLocal() as db:
        try:
            print(f"🔄 [Worker] Generating daily statistics...")
            today = datetime.now().date()
            today_start = datetime(today.year, today.month, today.day)
            today_end = today_start + timedelta(days=1)
            
            conversations_today = db.query(Conversation).filter(
                Conversation.created_at >= today_start,
                Conversation.created_at < today_end
            ).count()
            
            messages_today = db.query(Message).filter(
                Message.created_at >= today_start,
                Message.created_at < today_end
            ).count()
            
            print(f"✓ [Worker] Daily stats: {conversations_today} conversations, {messages_today} messages")
            return {
                "success": True,
                "date": str(today),
                "conversations": conversations_today,
                "messages": messages_today
            }
        except Exception as e:
            print(f"❌ [Worker] Daily stats error: {e}")
            return {"success": False, "error": str(e)}


# ========== WORKER SETTINGS ==========
class WorkerSettings:
    """Configuration for ARQ worker"""
    
    functions = [
        embed_document_job,
        summarize_conversation_job,
        process_ocr_job,
        generate_embedding_batch_job,
        cleanup_old_cache_job,
        generate_daily_stats_job
    ]
    
    concurrent_jobs = 5
    job_timeout = 3600
    health_check_interval = 30
    log_level = "INFO"
    
    # Số lần thử tối đa mặc định của ARQ (Dự phòng nếu logic code không handle)
    max_tries = 5 


# ========== TEST FUNCTION ==========
async def test_worker():
    """Test worker connectivity"""
    try:
        from core.queue import init_queue, get_task_status
        
        pool = await init_queue()
        print("✓ Worker pool initialized")
        
        job = await pool.enqueue_job('embed_document_job', 1, "test content", 1)
        print(f"✓ Test job enqueued: {job.job_id}")
        
        status = await get_task_status(job.job_id)
        print(f"✓ Job status: {status}")
        
        await pool.close()
        
    except Exception as e:
        print(f"❌ Worker test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_worker())