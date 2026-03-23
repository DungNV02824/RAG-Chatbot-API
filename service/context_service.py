from sqlalchemy.orm import Session
from typing import List, Dict
from models.message import Message
from core.config import SLIDING_WINDOW_SIZE, SUMMARIZATION_THRESHOLD
import redis
import json
from core.config import REDIS_URL

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def get_context_window(
    db: Session,
    conversation_id: int,
    window_size: int = None
) -> tuple:
    """
    Get sliding window of recent messages for context.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        window_size: Number of messages to include (default: SLIDING_WINDOW_SIZE)
    
    Returns:
        (messages, has_older_messages) - tuple of messages and flag indicating
        if there are older messages not included in the window
    """
    if window_size is None:
        window_size = SLIDING_WINDOW_SIZE
    
    # Get total message count
    total_count = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).count()
    
    # Get recent messages using sliding window
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.desc()).limit(window_size).all()
    
    messages = list(reversed(messages))  # Reverse to chronological order
    
    # Check if there are older messages beyond the window
    has_older = total_count > window_size
    
    return messages, has_older


def build_context_with_summary(
    db: Session,
    conversation_id: int,
    window_size: int = None
) -> Dict[str, str]:
    """
    Build context for LLM that includes:
    - Summary of old conversation (if applicable)
    - Recent messages in sliding window
    
    Returns:
        {
            "summary": "...",  # Summary of older messages
            "recent_messages": "...",  # Recent message window
            "full_context": "..."  # Complete context
        }
    """
    if window_size is None:
        window_size = SLIDING_WINDOW_SIZE
    
    messages, has_older = get_context_window(db, conversation_id, window_size)
    
    summary_text = ""
    
    # If there are older messages, try to get or create summary
    if has_older:
        summary_text = get_cached_summary(conversation_id)
        
        if not summary_text:
            # Queue summarization task for older messages
            try:
                from core.queue import enqueue_task
                from workers import summarize_conversation_job
                from models.conversation import Conversation
                
                # Get conversation for tenant_id
                conv = db.query(Conversation).filter(
                    Conversation.id == conversation_id
                ).first()
                
                if conv:
                    # Non-blocking: enqueue but continue
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    loop.run_until_complete(
                        enqueue_task(
                            summarize_conversation_job,
                            conversation_id,
                            conv.tenant_id
                        )
                    )
            except Exception as e:
                print(f"Could not enqueue summarization task: {e}")
                pass  # Silently fail - don't block response
    
    # Build recent messages text
    recent_text = ""
    for msg in messages:
        role = "Khách hàng" if msg.role == "user" else "Trợ lý"
        recent_text += f"{role}: {msg.content}\n"
    
    # Build full context
    if summary_text:
        full_context = f"=== TÓÓM LẠI HỘI THOẠI CŨ ===\n{summary_text}\n\n=== HỘI THOẠI GẦN ĐÂY ===\n{recent_text}"
    else:
        full_context = f"=== HỘI THOẠI GẦN ĐÂY ===\n{recent_text}"
    
    return {
        "summary": summary_text,
        "recent_messages": recent_text.strip(),
        "full_context": full_context.strip()
    }


def cache_summary(conversation_id: int, summary: str, ttl: int = 86400) -> bool:
    """Cache conversation summary in Redis"""
    try:
        key = f"conversation_summary:{conversation_id}"
        redis_client.setex(key, ttl, summary)
        return True
    except Exception as e:
        print(f"Error caching summary: {e}")
        return False


def get_cached_summary(conversation_id: int) -> str:
    """Get cached summary from Redis"""
    try:
        key = f"conversation_summary:{conversation_id}"
        summary = redis_client.get(key)
        return summary or ""
    except Exception as e:
        print(f"Error getting cached summary: {e}")
        return ""


def invalidate_summary_cache(conversation_id: int) -> bool:
    """Invalidate cached summary"""
    try:
        key = f"conversation_summary:{conversation_id}"
        redis_client.delete(key)
        return True
    except Exception as e:
        print(f"Error invalidating summary cache: {e}")
        return False


def get_message_count(db: Session, conversation_id: int) -> int:
    """Get total message count for a conversation"""
    return db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).count()


def should_summarize(db: Session, conversation_id: int) -> bool:
    """Check if conversation should be summarized"""
    count = get_message_count(db, conversation_id)
    return count > SUMMARIZATION_THRESHOLD


def get_context_stats(db: Session, conversation_id: int) -> Dict:
    """Get conversation context statistics"""
    total_count = get_message_count(db, conversation_id)
    messages, has_older = get_context_window(db, conversation_id)
    summary = get_cached_summary(conversation_id)
    
    return {
        "total_messages": total_count,
        "window_size": len(messages),
        "max_window": SLIDING_WINDOW_SIZE,
        "has_older_messages": has_older,
        "has_summary": bool(summary),
        "should_summarize": should_summarize(db, conversation_id)
    }
