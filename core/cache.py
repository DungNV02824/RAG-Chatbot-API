import json
import redis
import asyncio
from typing import List, Optional, Sequence, Tuple
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
except Exception:
    embedding_model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')


def _cache_index_key(tenant_id: int) -> str:
    """Redis SET member = full cache key string (avoids SCAN over keyspace)."""
    return f"semantic_cache:index:{tenant_id}"


def _batch_cosine_best(
    query_embedding: Sequence[float],
    rows: List[Tuple[Sequence[float], str]],
) -> Tuple[Optional[str], float]:
    """Vectorized cosine similarity — one numpy pass instead of per-key work."""
    import numpy as np

    if not rows:
        return None, 0.0

    q = np.asarray(query_embedding, dtype=np.float32)
    nq = np.linalg.norm(q)
    if nq > 0:
        q = q / nq
    else:
        return None, 0.0

    embeddings = np.asarray([np.asarray(r[0], dtype=np.float32) for r in rows], dtype=np.float32)
    responses = [r[1] for r in rows]

    norms = np.linalg.norm(embeddings, axis=1)
    norms = np.where(norms > 0, norms, 1.0)
    embeddings = embeddings / norms[:, np.newaxis]

    sims = embeddings @ q
    idx = int(np.argmax(sims))
    return responses[idx], float(sims[idx])


def get_semantic_embedding(text: str) -> list:
    """Get semantic embedding for a text"""
    return embedding_model.encode(text, convert_to_numpy=True).tolist()


def semantic_similarity(embedding1: list, embedding2: list) -> float:
    """Calculate cosine similarity between two embeddings (single-pair; prefer _batch_cosine_best for many)."""
    import numpy as np

    emb1 = np.array(embedding1)
    emb2 = np.array(embedding2)

    similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
    return float(similarity)


def get_cache_key(tenant_id: int, question: str) -> str:
    """Generate cache key for a question"""
    return f"semantic_cache:{tenant_id}:{hash(question)}"


def _tenant_cache_keys_sync(tenant_id: int) -> List[str]:
    """Resolve cache keys for tenant: indexed SET first, then legacy SCAN + lazy index backfill."""
    pattern = f"semantic_cache:{tenant_id}:*"
    index_key = _cache_index_key(tenant_id)
    keys = list(redis_client.smembers(index_key))
    if not keys:
        keys = list(redis_client.scan_iter(pattern))
        if keys:
            redis_client.sadd(index_key, *keys)
    keys = [k for k in keys if not k.startswith("semantic_cache:index:")]
    stale = [k for k in keys if not redis_client.exists(k)]
    if stale:
        redis_client.srem(index_key, *stale)
        keys = [k for k in keys if k not in stale]
    return keys


def _load_cache_rows_sync(cache_keys: List[str]) -> List[Tuple[List[float], str]]:
    if not cache_keys:
        return []
    pipe = redis_client.pipeline()
    for k in cache_keys:
        pipe.get(k)
    raw_vals = pipe.execute()
    rows: List[Tuple[List[float], str]] = []
    for raw in raw_vals:
        if not raw:
            continue
        try:
            data = json.loads(raw)
            emb = data.get("embedding")
            resp = data.get("response")
            if emb is not None and resp:
                rows.append((emb, resp))
        except json.JSONDecodeError:
            continue
    return rows


async def get_cached_response(tenant_id: int, question: str) -> Optional[Tuple[str, float]]:
    try:
        question_embedding = await asyncio.to_thread(get_semantic_embedding, question)

        def _lookup_sync():
            keys = _tenant_cache_keys_sync(tenant_id)
            rows = _load_cache_rows_sync(keys)
            return _batch_cosine_best(question_embedding, rows)

        best_response, best_similarity = await asyncio.to_thread(_lookup_sync)

        if best_similarity >= SEMANTIC_SIMILARITY_THRESHOLD and best_response is not None:
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
        tid = int(tenant_id)
        question_embedding = await asyncio.to_thread(get_semantic_embedding, question)

        cache_key = get_cache_key(tid, question)

        cache_data = {
            "question": question,
            "response": response,
            "embedding": question_embedding
        }

        payload = json.dumps(cache_data)
        index_key = _cache_index_key(tid)

        def _write_sync():
            pipe = redis_client.pipeline()
            pipe.setex(cache_key, SEMANTIC_CACHE_TTL, payload)
            pipe.sadd(index_key, cache_key)
            pipe.execute()

        await asyncio.to_thread(_write_sync)

        return True

    except Exception as e:
        print(f"Error setting cached response: {e}")
        return False


def invalidate_cache(tenant_id: int) -> int:
    try:
        pattern = f"semantic_cache:{tenant_id}:*"
        index_key = _cache_index_key(tenant_id)
        keys = list(redis_client.smembers(index_key))
        if not keys:
            keys = [k for k in redis_client.scan_iter(pattern) if not k.startswith("semantic_cache:index:")]

        if keys:
            redis_client.delete(*keys)
        redis_client.delete(index_key)

        return len(keys)

    except Exception as e:
        print(f"Error invalidating cache: {e}")
        return 0


def get_cache_stats(tenant_id: int) -> dict:
    try:
        keys = _tenant_cache_keys_sync(tenant_id)

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
