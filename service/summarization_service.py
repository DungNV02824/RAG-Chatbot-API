from sqlalchemy.orm import Session
from typing import Optional
from models.message import Message
from models.conversation import Conversation
from openai import OpenAI
from core.config import OPENAI_API_KEY, CHAT_MODEL, SUMMARY_MAX_TOKENS
from service.context_service import cache_summary, invalidate_summary_cache

client = OpenAI(api_key=OPENAI_API_KEY)


async def summarize_conversation(
    db: Session,
    conversation_id: int,
    tenant_id: int,
    threshold: int = None
) -> Optional[str]:
    """
    Summarize old messages in a conversation to save tokens.
    Called automatically when conversation gets too long.
    
    Args:
        db: Database session
        conversation_id: ID of conversation to summarize
        tenant_id: Tenant ID
        threshold: Messages count threshold (default: SUMMARIZATION_THRESHOLD)
    
    Returns:
        Summary text or None if summarization failed
    """
    from core.config import SUMMARIZATION_THRESHOLD
    
    if threshold is None:
        threshold = SUMMARIZATION_THRESHOLD
    
    try:
        # Get conversation
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            return None
        
        # Get all messages for this conversation
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
        
        if len(messages) < threshold:
            return None
        
        # Build text to summarize (exclude last N messages)
        from core.config import SLIDING_WINDOW_SIZE
        messages_to_summarize = messages[:-SLIDING_WINDOW_SIZE]
        
        if not messages_to_summarize:
            return None
        
        conversation_text = ""
        for msg in messages_to_summarize:
            role = "Khách hàng" if msg.role == "user" else "Trợ lý"
            conversation_text += f"{role}: {msg.content}\n"
        
        # Call OpenAI to summarize
        summary = await generate_summary(conversation_text)
        
        if summary:
            # Cache the summary
            cache_summary(conversation_id, summary)
            
            print(f"✓ Conversation {conversation_id} summarized: {len(summary)} chars")
            return summary
        
        return None
        
    except Exception as e:
        print(f"✗ Error summarizing conversation {conversation_id}: {e}")
        return None


async def generate_summary(
    content: str,
    max_tokens: int = None,
    language: str = "vi"
) -> Optional[str]:
    """
    Generate AI-powered summary of conversation content.
    
    Args:
        content: Text to summarize
        max_tokens: Maximum tokens for summary (default: SUMMARY_MAX_TOKENS)
        language: Language of content (vi, en, etc.)
    
    Returns:
        Summary text or None if generation failed
    """
    if max_tokens is None:
        max_tokens = SUMMARY_MAX_TOKENS
    
    try:
        # Build prompt for summarization
        if language == "vi":
            system_prompt = (
                "Bạn là chuyên gia tóm tắt hội thoại. "
                "Hãy tóm tắt nội dung hội thoại sau một cách ngắn gọn nhất, "
                "giữ lại những thông tin quan trọng về khách hàng (tên, điều kiện, yêu cầu) "
                "và các vấn đề được thảo luận."
            )
            
            user_prompt = (
                f"Hãy tóm tắt nội dung hội thoại sau bằng tiếng Việt, "
                f"trong giới hạn {max_tokens} tokens:\n\n{content}"
            )
        else:
            system_prompt = (
                "You are an expert at summarizing conversations. "
                "Summarize the following conversation concisely, "
                "retaining key information about customers and topics discussed."
            )
            
            user_prompt = (
                f"Please summarize the following conversation "
                f"in English, within {max_tokens} tokens:\n\n{content}"
            )
        
        # Call OpenAI
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None


def get_summary_stats(db: Session, conversation_id: int) -> dict:
    """Get statistics about conversation summarization"""
    from service.context_service import get_cached_summary, get_message_count
    
    total_messages = get_message_count(db, conversation_id)
    summary = get_cached_summary(conversation_id)
    
    from core.config import SUMMARIZATION_THRESHOLD, SLIDING_WINDOW_SIZE
    
    return {
        "total_messages": total_messages,
        "summary_threshold": SUMMARIZATION_THRESHOLD,
        "sliding_window_size": SLIDING_WINDOW_SIZE,
        "needs_summarization": total_messages > SUMMARIZATION_THRESHOLD,
        "has_summary": bool(summary),
        "summary_length": len(summary) if summary else 0,
        "estimated_token_savings": (
            (total_messages - SLIDING_WINDOW_SIZE) * 10  # Rough estimate
            if total_messages > SLIDING_WINDOW_SIZE else 0
        )
    }
