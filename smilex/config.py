import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "stock.db")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

DEFAULT_START_DATE = "20210101"
INITIAL_CAPITAL = 100000.0

MA_SHORT_PERIOD = 5
MA_LONG_PERIOD = 20
RSI_PERIOD = 14
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2

SCANNER_MIN_LISTED_DAYS = 60
SCANNER_VOLUME_RATIO_MIN = 1.5

DASHBOARD_PORT = 8501
DASHBOARD_HOST = "0.0.0.0"

# AI Analysis Configuration
AI_MODEL = os.environ.get("SMILEX_AI_MODEL", "deepseek/deepseek-chat")
AI_API_KEY = os.environ.get("SMILEX_AI_API_KEY", "")
AI_API_BASE = os.environ.get("SMILEX_AI_API_BASE", "")
AI_INDICES = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
}
