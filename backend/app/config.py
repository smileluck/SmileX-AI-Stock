import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "stock.db"

LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")
MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "MiniMax-M3")
MODEL_NEWS_SCORER = os.getenv("MODEL_NEWS_SCORER", "MiniMax-M3")
MODEL_CHAT = os.getenv("MODEL_CHAT", "MiniMax-M3")

LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "3"))
LLM_QUEUE_TIMEOUT = float(os.getenv("LLM_QUEUE_TIMEOUT", "300"))

# CORS：逗号分隔的 origin 列表；"*" 表示放开（仅本地/开发用）
_CORS_RAW = os.getenv("CORS_ALLOWED_ORIGINS", "*").strip()
if _CORS_RAW == "*":
    CORS_ALLOWED_ORIGINS = ["*"]
else:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]
