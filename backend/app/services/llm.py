from openai import OpenAI

from app.config import LITELLM_PROXY_URL, LITELLM_MASTER_KEY


def _get_client() -> OpenAI:
    kwargs: dict = {"base_url": f"{LITELLM_PROXY_URL}/v1"}
    if LITELLM_MASTER_KEY:
        kwargs["api_key"] = LITELLM_MASTER_KEY
    else:
        kwargs["api_key"] = "sk-placeholder"
    return OpenAI(**kwargs)


def chat(messages: list[dict], model: str = "MiniMax-M3", **kwargs) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content


def test_connection() -> dict:
    client = _get_client()
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        return {"success": True, "models": model_ids}
    except Exception as e:
        return {"success": False, "error": str(e)}
