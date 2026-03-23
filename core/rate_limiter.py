# import redis
# import time
# from typing import Tuple
# from core.config import (
#     REDIS_URL,
#     RATE_LIMIT_REQUESTS,
#     RATE_LIMIT_WINDOW,
#     RATE_LIMIT_BURST
# )

# redis_client = redis.from_url(REDIS_URL, decode_responses=True)


# def get_rate_limit_key(identifier: str, resource: str = "api") -> str:
#     """Generate rate limit key"""
#     return f"rate_limit:{identifier}:{resource}"


# def check_rate_limit(identifier: str, resource: str = "api") -> Tuple[bool, dict]:
#     """
#     Check if request is allowed using Token Bucket algorithm.
    
#     Args:
#         identifier: tenant_id or api_key
#         resource: API endpoint or resource name
    
#     Returns:
#         (is_allowed: bool, info: dict with remaining_tokens, reset_time)
#     """
#     try:
#         key = get_rate_limit_key(identifier, resource)
#         current_time = time.time()
        
#         # Get current bucket state
#         bucket_data = redis_client.hgetall(key)
        
#         if not bucket_data:
#             # First request - initialize bucket
#             tokens = RATE_LIMIT_REQUESTS
#             last_refill = current_time
#             redis_client.hset(key, mapping={
#                 "tokens": tokens,
#                 "last_refill": last_refill
#             })
#             redis_client.expire(key, RATE_LIMIT_WINDOW * 2)
            
#             return True, {
#                 "remaining": tokens - 1,
#                 "reset_in": RATE_LIMIT_WINDOW,
#                 "limit": RATE_LIMIT_REQUESTS
#             }
        
#         tokens = float(bucket_data.get("tokens", RATE_LIMIT_REQUESTS))
#         last_refill = float(bucket_data.get("last_refill", current_time))
        
#         # Refill tokens based on time elapsed
#         time_passed = current_time - last_refill
#         refill_rate = RATE_LIMIT_REQUESTS / RATE_LIMIT_WINDOW  # tokens per second
#         tokens_to_add = time_passed * refill_rate
        
#         tokens = min(tokens + tokens_to_add, RATE_LIMIT_BURST)
        
#         # Check if we can consume a token
#         if tokens >= 1:
#             tokens -= 1
#             is_allowed = True
#         else:
#             is_allowed = False
        
#         # Update bucket
#         redis_client.hset(key, mapping={
#             "tokens": tokens,
#             "last_refill": current_time
#         })
#         redis_client.expire(key, RATE_LIMIT_WINDOW * 2)
        
#         reset_in = RATE_LIMIT_WINDOW if tokens == 0 else (
#             (RATE_LIMIT_WINDOW - (current_time % RATE_LIMIT_WINDOW))
#         )
        
#         return is_allowed, {
#             "remaining": int(tokens),
#             "reset_in": int(reset_in),
#             "limit": RATE_LIMIT_REQUESTS
#         }
        
#     except Exception as e:
#         print(f"Rate limit check error: {e}")
#         # Fail open - allow request if Redis unavailable
#         return True, {
#             "remaining": RATE_LIMIT_REQUESTS,
#             "reset_in": RATE_LIMIT_WINDOW,
#             "limit": RATE_LIMIT_REQUESTS,
#             "error": str(e)
#         }


# def get_rate_limit_status(identifier: str, resource: str = "api") -> dict:
#     """Get current rate limit status"""
#     try:
#         key = get_rate_limit_key(identifier, resource)
#         bucket_data = redis_client.hgetall(key)
        
#         if not bucket_data:
#             return {
#                 "remaining": RATE_LIMIT_REQUESTS,
#                 "limit": RATE_LIMIT_REQUESTS,
#                 "requests_in_window": 0
#             }
        
#         tokens = float(bucket_data.get("tokens", RATE_LIMIT_REQUESTS))
        
#         return {
#             "remaining": int(tokens),
#             "limit": RATE_LIMIT_REQUESTS,
#             "burst_capacity": RATE_LIMIT_BURST
#         }
        
#     except Exception as e:
#         print(f"Error getting rate limit status: {e}")
#         return {"error": str(e)}


# def reset_rate_limit(identifier: str, resource: str = "api") -> bool:
#     """Reset rate limit for an identifier"""
#     try:
#         key = get_rate_limit_key(identifier, resource)
#         redis_client.delete(key)
#         return True
#     except Exception as e:
#         print(f"Error resetting rate limit: {e}")
#         return False


# def reset_all_rate_limits() -> int:
#     """Reset all rate limits (useful for admin operations)"""
#     try:
#         pattern = "rate_limit:*"
#         keys = redis_client.keys(pattern)
        
#         if keys:
#             redis_client.delete(*keys)
        
#         return len(keys)
        
#     except Exception as e:
#         print(f"Error resetting all rate limits: {e}")
#         return 0



import redis
import time
from typing import Tuple

from core.config import REDIS_URL

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# ==============================
# CONFIG
# ==============================
DEFAULT_CONFIG = {
    "requests": 10,
    "window": 60,
    "burst": 20,
    "hard_limit": 100
}

FAIL_OPEN = True


# ==============================
# LUA SCRIPT (ATOMIC TOKEN BUCKET)
# ==============================
HARD_LIMIT_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])

local count = redis.call("INCR", key)

if count == 1 then
    redis.call("EXPIRE", key, window)
end

return count
"""
LUA_SCRIPT = """
local key = KEYS[1]

local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "last_refill")

local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = max_tokens
    last_refill = now
end

local delta = math.max(0, now - last_refill)
local refill = delta * refill_rate
tokens = math.min(tokens + refill, capacity)

local allowed = 0

if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call("HMSET", key,
    "tokens", tokens,
    "last_refill", now
)

local ttl = tonumber(ARGV[5])
redis.call("EXPIRE", key, ttl)

local reset_in = 0
if refill_rate > 0 and tokens < 1 then
    reset_in = (1 - tokens) / refill_rate
else
    reset_in = 0
end

return {allowed, tokens, reset_in}
"""


# ==============================
# HELPERS
# ==============================
def get_rate_limit_key(identifier: str, resource: str, scope: str):
    return f"rate_limit:{scope}:{identifier}:{resource}"


# def get_hard_limit_key(identifier: str):
#     return f"hard_limit:{identifier}"
def get_hard_limit_key(identifier: str, resource: str, scope: str):
    return f"hard_limit:{scope}:{identifier}:{resource}"

def get_rate_limit_config(identifier: str):
    """
    Có thể load từ DB/Redis theo tenant/user
    """
    return DEFAULT_CONFIG


# ==============================
# HARD LIMIT (fixed window)
# ==============================
def check_hard_limit(identifier: str, resource: str, scope: str, limit: int, window: int):
    key = get_hard_limit_key(identifier, resource, scope)

    count = redis_client.eval(
        HARD_LIMIT_LUA,
        1,
        key,
        window
    )

    return int(count) <= limit


# ==============================
# MAIN FUNCTION
# ==============================
def check_rate_limit(
    identifier: str,
    resource: str = "api",
    scope: str = "tenant"
) -> Tuple[bool, dict]:

    try:
        # ===== LOAD CONFIG =====
        config = get_rate_limit_config(identifier)

        max_tokens = config["requests"]
        window = config["window"]
        burst = config["burst"]
        hard_limit = config["hard_limit"]

        refill_rate = max_tokens / window if window > 0 else 0
        now = time.time()

        # ===== HARD LIMIT =====
        if not check_hard_limit(identifier, resource, scope, hard_limit, window):
            return False, {
                "error": "hard_limit_exceeded",
                "message": "Too many requests (hard limit)",
                "limit": hard_limit,
                "remaining": 0,
                "reset_in": window,
                "retry_after": window
            }

        # ===== TOKEN BUCKET (ATOMIC) =====
        key = get_rate_limit_key(identifier, resource, scope)
        ttl = window * 2
        result = redis_client.eval(
            LUA_SCRIPT,
            1,
            key,
            max_tokens,
            refill_rate,
            burst,
            now,
            ttl
        )

        allowed = bool(result[0])
        tokens = float(result[1])
        reset_in = float(result[2])

        return allowed, {
            "remaining": int(tokens),
            "limit": max_tokens,
            "reset_in": round(reset_in, 2)
        }

    except Exception as e:
        print(f"Rate limit error: {e}")

        if FAIL_OPEN:
            return True, {
                "remaining": DEFAULT_CONFIG["requests"],
                "reset_in": DEFAULT_CONFIG["window"],
                "limit": DEFAULT_CONFIG["requests"],
                "error": str(e)
            }
        else:
            return False, {
                "error": "rate_limiter_down"
            }


# ==============================
# STATUS
# ==============================
def get_rate_limit_status(identifier: str, resource: str = "api", scope: str = "tenant"):
    try:
        key = get_rate_limit_key(identifier, resource, scope)
        data = redis_client.hgetall(key)

        if not data:
            return {
                "remaining": DEFAULT_CONFIG["requests"],
                "limit": DEFAULT_CONFIG["requests"]
            }

        return {
            "remaining": int(float(data.get("tokens", 0))),
            "limit": DEFAULT_CONFIG["requests"]
        }

    except Exception as e:
        return {"error": str(e)}


# ==============================
# RESET
# ==============================
def reset_rate_limit(identifier: str, resource: str = "api", scope: str = "tenant"):
    try:
        key = get_rate_limit_key(identifier, resource, scope)
        redis_client.delete(key)
        return True
    except:
        return False