import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("MODEL_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}" if REDIS_PASSWORD else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Cache Settings
SEMANTIC_CACHE_TTL = int(os.getenv("SEMANTIC_CACHE_TTL", 86400))  # 24 hours
SEMANTIC_SIMILARITY_THRESHOLD = float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", 0.95))

# Rate Limiting Settings
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 100))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # seconds
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", 10))  # burst size

# Context Settings
SLIDING_WINDOW_SIZE = int(os.getenv("SLIDING_WINDOW_SIZE", 10))  # last N messages
SUMMARIZATION_THRESHOLD = int(os.getenv("SUMMARIZATION_THRESHOLD", 50))  # messages count
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", 500))

# LLM Billing / Hard Limit
HARD_LIMIT_USD_PER_MONTH = float(os.getenv("HARD_LIMIT_USD_PER_MONTH", 5.0))
INPUT_TOKEN_PRICE_PER_1K = float(os.getenv("INPUT_TOKEN_PRICE_PER_1K", 0.0025))
OUTPUT_TOKEN_PRICE_PER_1K = float(os.getenv("OUTPUT_TOKEN_PRICE_PER_1K", 0.01))
