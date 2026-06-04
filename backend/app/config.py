import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "stock.db"

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

LLM_DEFAULT_PROVIDER = os.getenv("LLM_DEFAULT_PROVIDER", "")
LLM_DEFAULT_MODEL = os.getenv("LLM_DEFAULT_MODEL", "")
LLM_DEFAULT_API_KEY = os.getenv("LLM_DEFAULT_API_KEY", "")
LLM_DEFAULT_BASE_URL = os.getenv("LLM_DEFAULT_BASE_URL", "")
