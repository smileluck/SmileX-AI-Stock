import json
import logging
import re
import time

from openai import OpenAI

from app.config import LITELLM_PROXY_URL, LITELLM_MASTER_KEY, MODEL_ANALYSIS, MODEL_NEWS_SCORER, MODEL_CHAT

logger = logging.getLogger(__name__)

_ENV_DEFAULTS = {
    "analysis": MODEL_ANALYSIS,
    "news_scorer": MODEL_NEWS_SCORER,
    "chat": MODEL_CHAT,
    "research_pick": MODEL_ANALYSIS,
}

_CLIENT: OpenAI | None = None
_MODEL_CACHE: dict[str, tuple[float, str]] = {}
_MODEL_CACHE_TTL = 60.0


def _get_client() -> OpenAI:
    # timeout=180s：长输出 JSON（推荐/复盘/涨停）单次约 60-120s，60s 会超时；
    # max_retries=1：SDK 默认 2 次重试会把超时拉到 3x，单次失败快速反馈更可控。
    global _CLIENT
    if _CLIENT is None:
        kwargs: dict = {"base_url": f"{LITELLM_PROXY_URL}/v1", "timeout": 180.0, "max_retries": 1}
        kwargs["api_key"] = LITELLM_MASTER_KEY or "sk-placeholder"
        _CLIENT = OpenAI(**kwargs)
    return _CLIENT


def invalidate_model_cache(function_key: str | None = None) -> None:
    if function_key is None:
        _MODEL_CACHE.clear()
    else:
        _MODEL_CACHE.pop(function_key, None)


def _resolve_model(function_key: str) -> str:
    cached = _MODEL_CACHE.get(function_key)
    now = time.monotonic()
    if cached and now - cached[0] < _MODEL_CACHE_TTL:
        return cached[1]

    model_name = _ENV_DEFAULTS.get(function_key, "MiniMax-M3")
    try:
        from app.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT model_name FROM model_config WHERE function_key = ?",
                (function_key,),
            ).fetchone()
            if row:
                model_name = row["model_name"]
        finally:
            conn.close()
    except Exception:
        logger.debug("DB lookup for model_config failed, using env default", exc_info=True)

    _MODEL_CACHE[function_key] = (now, model_name)
    return model_name


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


_FENCED_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_response(text: str, expect: str = "any"):
    """从 LLM 输出抽取 JSON。

    支持三种形态：
      1. ```json ... ``` 围栏（任意大小写、可选 json 标记）
      2. 裸 JSON（``[...]``、``{...}``）
      3. 兜底：截取第一个 ``[`` / ``{`` 到最后一个 ``]`` / ``}``

    expect:
      - "object": 仅接受 dict，否则返回 ``{}``
      - "array":  仅接受 list，否则返回 ``[]``
      - "any" (默认): 解析成功则原样返回，失败时按 default 推断（``{}``）
    """
    if not text or not isinstance(text, str):
        return [] if expect == "array" else {}

    candidates: list[str] = []
    for m in _FENCED_RE.finditer(text):
        candidates.append(m.group(1).strip())
    candidates.append(text.strip())

    if expect == "array":
        for c in candidates:
            try:
                data = json.loads(c)
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
        start = text.find("[")
        end = text.rfind("]")
        if 0 <= start < end:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    if expect == "object":
        for c in candidates:
            try:
                data = json.loads(c)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
    return {}
