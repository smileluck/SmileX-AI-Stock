from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import MODEL_ANALYSIS, MODEL_NEWS_SCORER, MODEL_CHAT
from app.database import get_connection
from app.services.llm import test_connection

router = APIRouter(prefix="/ai", tags=["ai"])

AI_FUNCTIONS = [
    {"key": "analysis", "label": "大盘分析", "description": "市场分析和预测"},
    {"key": "news_scorer", "label": "新闻评分", "description": "新闻影响力和分类评分"},
    {"key": "chat", "label": "AI对话", "description": "通用AI对话助手"},
    {"key": "sector_analysis", "label": "板块分析", "description": "板块深度分析报告"},
    {"key": "daily_report", "label": "AI收盘报告", "description": "每日综合收盘分析"},
    {"key": "stock_recommendation", "label": "AI个股推荐", "description": "个股投资推荐"},
]

_ENV_DEFAULTS = {
    "analysis": MODEL_ANALYSIS,
    "news_scorer": MODEL_NEWS_SCORER,
    "chat": MODEL_CHAT,
    "sector_analysis": MODEL_ANALYSIS,
    "daily_report": MODEL_ANALYSIS,
    "stock_recommendation": MODEL_ANALYSIS,
}


@router.get("/model-config")
def get_model_configs():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT function_key, model_name FROM model_config").fetchall()
        db_map = {r["function_key"]: r["model_name"] for r in rows}
    finally:
        conn.close()

    result = []
    for func in AI_FUNCTIONS:
        key = func["key"]
        result.append({
            "function_key": key,
            "label": func["label"],
            "description": func["description"],
            "model_name": db_map.get(key) or _ENV_DEFAULTS.get(key, "MiniMax-M3"),
            "source": "database" if key in db_map else "env_default",
        })
    return result


class ModelConfigItem(BaseModel):
    function_key: str
    model_name: str


class UpdateModelConfigsRequest(BaseModel):
    configs: list[ModelConfigItem]


@router.put("/model-config")
def update_model_configs(req: UpdateModelConfigsRequest):
    conn = get_connection()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for c in req.configs:
            conn.execute(
                "INSERT INTO model_config (function_key, model_name, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(function_key) DO UPDATE SET model_name = excluded.model_name, updated_at = excluded.updated_at",
                (c.function_key, c.model_name, now),
            )
        conn.commit()
    finally:
        conn.close()
    return {"success": True}


@router.get("/model-config/functions")
def get_ai_functions():
    return AI_FUNCTIONS


@router.get("/model-config/available-models")
def get_available_models():
    result = test_connection()
    if result["success"]:
        return {"models": result["models"]}
    return {"models": [], "error": result.get("error")}
