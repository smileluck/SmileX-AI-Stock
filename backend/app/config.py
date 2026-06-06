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
MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "analysis")
MODEL_NEWS_SCORER = os.getenv("MODEL_NEWS_SCORER", "news-scorer")
MODEL_CHAT = os.getenv("MODEL_CHAT", "MiniMax-M3")
