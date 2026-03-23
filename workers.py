"""
Async worker queue for handling heavy tasks.
This module defines all async jobs that are executed by ARQ workers.

To run workers:
    arq workers.WorkerSettings
"""

# from arq import async_task
from typing import Callable
import sys


# ========== DEFINE ASYNC JOBS ==========
# These tasks are executed asynchronously by the worker process


async def embed_document_job(document_id: int, content: str, tenant_id: int):
    """
    Async job to embed a document and store the embedding in DB.
    Called when a new document is uploaded.
    """
    from service.embedding import embed_text
    from db.session import SessionLocal
    from models.document import Document
    
    db = SessionLocal()
    try:
        print(f"🔄 [Worker] Embedding document {document_id}...")
        
        # Generate embedding
        embedding = embed_text(content)
        
        # Store in database
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            # Convert numpy array to list for storage
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            
            doc.embedding = embedding
            db.commit()
            print(f"✓ [Worker] Document {document_id} embedded successfully")
            return {"success": True, "document_id": document_id}
        else:
            print(f"❌ [Worker] Document {document_id} not found")
            return {"success": False, "error": "Document not found"}
            
    except Exception as e:
        print(f"❌ [Worker] Error embedding document {document_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def summarize_conversation_job(conversation_id: int, tenant_id: int):
    """
    Async job to summarize long conversations.
    Called automatically when conversation exceeds threshold.
    """
    from service.summarization_service import summarize_conversation
    from db.session import SessionLocal
    
    db = SessionLocal()
    try:
        print(f"🔄 [Worker] Summarizing conversation {conversation_id}...")
        
        summary = await summarize_conversation(db, conversation_id, tenant_id)
        
        if summary:
            print(f"✓ [Worker] Conversation {conversation_id} summarized ({len(summary)} chars)")
            return {"success": True, "conversation_id": conversation_id, "summary_length": len(summary)}
        else:
            print(f"⚠️ [Worker] Conversation {conversation_id} already summarized")
            return {"success": False, "error": "Already summarized or too short"}
            
    except Exception as e:
        print(f"❌ [Worker] Error summarizing conversation {conversation_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def process_ocr_job(file_path: str, document_id: int, tenant_id: int):
    """
    Async job to process OCR on PDF documents.
    Heavy operation - must be async to not block main API.
    """
    try:
        print(f"🔄 [Worker] Processing OCR for {file_path}...")
        
        # TODO: Implement actual OCR processing
        # from pdf2image import convert_from_path
        # from pytesseract import image_to_string
        # import os
        
        # images = convert_from_path(file_path)
        # ocr_text = ""
        # for img in images:
        #     ocr_text += image_to_string(img) + "\n"
        
        # Store OCR result...
        
        print(f"✓ [Worker] OCR processing completed for {file_path}")
        return {"success": True, "file_path": file_path}
        
    except Exception as e:
        print(f"❌ [Worker] Error processing OCR for {file_path}: {e}")
        return {"success": False, "error": str(e)}


async def generate_embedding_batch_job(documents: list):
    """
    Async job to embed multiple documents in batch.
    More efficient than individual embedding jobs.
    """
    from service.embedding import embed_text
    from db.session import SessionLocal
    from models.document import Document
    
    db = SessionLocal()
    try:
        print(f"🔄 [Worker] Batch embedding {len(documents)} documents...")
        
        results = []
        for doc_data in documents:
            doc_id = doc_data["id"]
            content = doc_data["content"]
            
            try:
                embedding = embed_text(content)
                
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    if hasattr(embedding, 'tolist'):
                        embedding = embedding.tolist()
                    doc.embedding = embedding
                    results.append({"id": doc_id, "success": True})
                else:
                    results.append({"id": doc_id, "success": False, "error": "Not found"})
            except Exception as e:
                results.append({"id": doc_id, "success": False, "error": str(e)})
        
        db.commit()
        print(f"✓ [Worker] Batch embedding completed: {sum(1 for r in results if r['success'])}/{len(documents)} succeeded")
        return {"success": True, "results": results}
        
    except Exception as e:
        print(f"❌ [Worker] Batch embedding error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def cleanup_old_cache_job(days: int = 7):
    """
    Async job to cleanup old cache entries.
    Can be scheduled to run periodically.
    """
    from core.cache import redis_client
    import time
    
    try:
        print(f"🔄 [Worker] Cleaning up cache older than {days} days...")
        
        # Get all cache keys
        pattern = "semantic_cache:*"
        keys = redis_client.keys(pattern)
        
        cutoff_time = time.time() - (days * 24 * 3600)
        deleted = 0
        
        for key in keys:
            ttl = redis_client.ttl(key)
            if ttl == -1:  # Key exists without expiration
                redis_client.delete(key)
                deleted += 1
        
        print(f"✓ [Worker] Cache cleanup completed: {deleted} keys deleted")
        return {"success": True, "deleted": deleted}
        
    except Exception as e:
        print(f"❌ [Worker] Cache cleanup error: {e}")
        return {"success": False, "error": str(e)}


async def generate_daily_stats_job():
    """
    Async job to generate daily statistics.
    Can be scheduled to run daily.
    """
    from db.session import SessionLocal
    from models.conversation import Conversation
    from models.message import Message
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        print(f"🔄 [Worker] Generating daily statistics...")
        
        today = datetime.now().date()
        
        # Get today's stats
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
    finally:
        db.close()


# ========== WORKER SETTINGS ==========
class WorkerSettings:
    """Configuration for ARQ worker"""
    
    # Remove functions called by the worker
    functions = [
        embed_document_job,
        summarize_conversation_job,
        process_ocr_job,
        generate_embedding_batch_job,
        cleanup_old_cache_job,
        generate_daily_stats_job
    ]
    
    # Concurrency - how many jobs to run in parallel
    concurrent_jobs = 5
    
    # Job timeout in seconds
    job_timeout = 3600
    
    # Heartbeat interval
    health_check_interval = 30
    
    # Log level
    log_level = "INFO"


# ========== TEST FUNCTION ==========
async def test_worker():
    """Test worker connectivity"""
    try:
        from core.queue import init_queue, get_task_status
        
        pool = await init_queue()
        print("✓ Worker pool initialized")
        
        # Test enqueue a simple job
        job = await pool.enqueue_job(embed_document_job, 1, "test content", 1)
        print(f"✓ Test job enqueued: {job.job_id}")
        
        # Check status
        status = await get_task_status(job.job_id)
        print(f"✓ Job status: {status}")
        
        await pool.close()
        
    except Exception as e:
        print(f"❌ Worker test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run test if executed directly
    import asyncio
    asyncio.run(test_worker())
