import json
import redis
import asyncio
from typing import Optional, Tuple
from sentence_transformers import SentenceTransformer
from core.config import (
    REDIS_URL,
    SEMANTIC_CACHE_TTL,
    SEMANTIC_SIMILARITY_THRESHOLD
)

# Initialize Redis with connection pooling
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Load embedding model for semantic similarity
try:
    embedding_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')
except:
    embedding_model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')


def get_semantic_embedding(text: str) -> list:
    """Get semantic embedding for a text"""
    return embedding_model.encode(text, convert_to_numpy=True).tolist()


def semantic_similarity(embedding1: list, embedding2: list) -> float:
    """Calculate cosine similarity between two embeddings"""
    import numpy as np
    
    emb1 = np.array(embedding1)
    emb2 = np.array(embedding2)
    
    similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
    return float(similarity)


def get_cache_key(tenant_id: int, question: str) -> str:
    """Generate cache key for a question"""
    return f"semantic_cache:{tenant_id}:{hash(question)}"
async def get_cached_response(tenant_id: int, question: str) -> Optional[Tuple[str, float]]:
    try:
        #  chạy embedding ở thread khác (tránh block)
        question_embedding = await asyncio.to_thread(get_semantic_embedding, question)

        pattern = f"semantic_cache:{tenant_id}:*"

        best_similarity = 0
        best_response = None

        
        for key in redis_client.scan_iter(pattern):
            cache_data = redis_client.get(key)
            if not cache_data:
                continue

            try:
                data = json.loads(cache_data)
                cached_embedding = data.get("embedding")
                cached_response = data.get("response")

                if not cached_embedding or not cached_response:
                    continue

                #  tính similarity ở thread khác
                similarity = await asyncio.to_thread(
                    semantic_similarity,
                    question_embedding,
                    cached_embedding
                )

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_response = cached_response

            except json.JSONDecodeError:
                continue

        if best_similarity >= SEMANTIC_SIMILARITY_THRESHOLD:
            return (best_response, best_similarity)

        return None

    except Exception as e:
        print(f"Error getting cached response: {e}")
        return None


async def set_cached_response(
    tenant_id: int,
    question: str,
    response: str
) -> bool:
    try:
        # ⚡ tránh block
        question_embedding = await asyncio.to_thread(get_semantic_embedding, question)

        cache_key = get_cache_key(tenant_id, question)

        cache_data = {
            "question": question,
            "response": response,
            "embedding": question_embedding
        }

        redis_client.setex(
            cache_key,
            SEMANTIC_CACHE_TTL,
            json.dumps(cache_data)
        )

        return True

    except Exception as e:
        print(f"Error setting cached response: {e}")
        return False


def invalidate_cache(tenant_id: int) -> int:
    try:
        pattern = f"semantic_cache:{tenant_id}:*"
        keys = list(redis_client.scan_iter(pattern))  

        if keys:
            redis_client.delete(*keys)

        return len(keys)

    except Exception as e:
        print(f"Error invalidating cache: {e}")
        return 0


def get_cache_stats(tenant_id: int) -> dict:
    try:
        pattern = f"semantic_cache:{tenant_id}:*"
        keys = list(redis_client.scan_iter(pattern))  

        total_size = 0
        for key in keys:
            total_size += redis_client.memory_usage(key) or 0

        return {
            "cached_queries": len(keys),
            "cache_size_bytes": total_size,
            "ttl_seconds": SEMANTIC_CACHE_TTL
        }

    except Exception as e:
        print(f"Error getting cache stats: {e}")
        return {"error": str(e)}
