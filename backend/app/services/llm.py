import logging

from openai import OpenAI

from app.config import LITELLM_PROXY_URL, LITELLM_MASTER_KEY, MODEL_ANALYSIS, MODEL_NEWS_SCORER, MODEL_CHAT

logger = logging.getLogger(__name__)

_ENV_DEFAULTS = {
    "analysis": MODEL_ANALYSIS,
    "news_scorer": MODEL_NEWS_SCORER,
    "chat": MODEL_CHAT,
}


def _get_client() -> OpenAI:
    kwargs: dict = {"base_url": f"{LITELLM_PROXY_URL}/v1", "timeout": 60.0}
    if LITELLM_MASTER_KEY:
        kwargs["api_key"] = LITELLM_MASTER_KEY
    else:
        kwargs["api_key"] = "sk-placeholder"
    return OpenAI(**kwargs)


def _resolve_model(function_key: str) -> str:
    try:
        from app.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT model_name FROM model_config WHERE function_key = ?",
                (function_key,),
            ).fetchone()
            if row:
                return row["model_name"]
        finally:
            conn.close()
    except Exception:
        logger.debug("DB lookup for model_config failed, using env default", exc_info=True)
    return _ENV_DEFAULTS.get(function_key, "MiniMax-M3")


def get_model_for_function(function_key: str) -> str:
    return _resolve_model(function_key)


def chat(messages: list[dict], model: str | None = None, **kwargs) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=model or _resolve_model("chat"),
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content


def analysis_chat(messages: list[dict], **kwargs) -> str:
    return chat(messages, model=_resolve_model("analysis"), **kwargs)


def score_news(messages: list[dict], **kwargs) -> str:
    return chat(messages, model=_resolve_model("news_scorer"), **kwargs)


def function_chat(function_key: str, messages: list[dict], **kwargs) -> str:
    return chat(messages, model=_resolve_model(function_key), **kwargs)


def test_connection() -> dict:
    client = _get_client()
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        return {"success": True, "models": model_ids}
    except Exception as e:
        return {"success": False, "error": str(e)}
