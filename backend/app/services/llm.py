from openai import OpenAI

from app.config import LITELLM_PROXY_URL, LITELLM_MASTER_KEY, MODEL_ANALYSIS, MODEL_NEWS_SCORER, MODEL_CHAT


def _get_client() -> OpenAI:
    kwargs: dict = {"base_url": f"{LITELLM_PROXY_URL}/v1"}
    if LITELLM_MASTER_KEY:
        kwargs["api_key"] = LITELLM_MASTER_KEY
    else:
        kwargs["api_key"] = "sk-placeholder"
    return OpenAI(**kwargs)


def chat(messages: list[dict], model: str | None = None, **kwargs) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=model or MODEL_CHAT,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content


def analysis_chat(messages: list[dict], **kwargs) -> str:
    return chat(messages, model=MODEL_ANALYSIS, **kwargs)


def score_news(messages: list[dict], **kwargs) -> str:
    return chat(messages, model=MODEL_NEWS_SCORER, **kwargs)


def test_connection() -> dict:
    client = _get_client()
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        return {"success": True, "models": model_ids}
    except Exception as e:
        return {"success": False, "error": str(e)}
