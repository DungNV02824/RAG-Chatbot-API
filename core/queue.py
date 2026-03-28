# core/queue.py
from typing import Any, Optional
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
    function_name: str, 
    *args,
    **kwargs
) -> str:
    """
    Enqueue an async task to be processed by ARQ workers.
    
    Args:
        function_name: String name of the function (e.g., 'embed_document_job')
        *args: Positional arguments for the job
        **kwargs: Keyword arguments for the job
    
    Returns:
        Job ID (string)
    """
    global _pool
    
    if not _pool:
        raise RuntimeError("Task queue not initialized. Call init_queue() first in app startup.")
    
    try:
        # Trong ARQ, tham số truyền vào enqueue_job là tên hàm dạng string
        job = await _pool.enqueue_job(function_name, *args, **kwargs)
        if job:
            return job.job_id
        return None
    except Exception as e:
        print(f"Error enqueueing task '{function_name}': {e}")
        raise


async def get_task_result(job_id: str) -> Optional[Any]:
    """Get result of a completed task"""
    global _pool
    if not _pool:
        raise RuntimeError("Task queue not initialized.")
    
    try:
        job = _pool.job(job_id)
        if job:
            return await job.result() # Cần await job.result() vì nó là coroutine
        return None
    except Exception as e:
        print(f"Error getting task result: {e}")
        return None


async def get_task_status(job_id: str) -> str:
    """Get status of a task (queued, in_progress, complete, not_found)"""
    global _pool
    if not _pool:
        raise RuntimeError("Task queue not initialized.")
    
    try:
        job = _pool.job(job_id)
        if not job:
            return "not_found"
        
        info = await job.info()
        if not info:
            return "not_found"
            
        status = await job.status()
        return status.value 
            
    except Exception as e:
        print(f"Error getting task status for {job_id}: {e}")
        return "error"

