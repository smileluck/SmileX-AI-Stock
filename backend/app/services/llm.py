import litellm

from app.models.ai_config import ConnectionTestResponse, PROVIDERS
from app.services.ai_config import get_decrypted_config, get_decrypted_default


def _build_litellm_model(provider: str, model: str) -> str:
    if provider in ("openai", "anthropic"):
        return model
    return f"{provider}/{model}"


def _get_config(config_id: int | None = None) -> dict:
    if config_id:
        config = get_decrypted_config(config_id)
    else:
        config = get_decrypted_default()
    if not config:
        raise ValueError("未找到可用的模型配置，请先在设置中配置 AI 模型")
    return config


def chat(messages: list[dict], config_id: int | None = None, **kwargs) -> str:
    config = _get_config(config_id)
    model = _build_litellm_model(config["provider"], config["model"])
    params = {
        "model": model,
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "api_key": config["api_key"],
    }
    if config["base_url"]:
        params["api_base"] = config["base_url"]
    params.update(kwargs)
    response = litellm.completion(**params)
    return response.choices[0].message.content


def test_connection(config_id: int | None = None, config_data: dict | None = None) -> ConnectionTestResponse:
    if config_data:
        provider = config_data["provider"]
        model = _build_litellm_model(provider, config_data["model"])
        api_key = config_data["api_key"]
        base_url = config_data.get("base_url", "")
    else:
        config = _get_config(config_id)
        provider = config["provider"]
        model = _build_litellm_model(provider, config["model"])
        api_key = config["api_key"]
        base_url = config["base_url"]

    try:
        params = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "api_key": api_key,
        }
        if base_url:
            params["api_base"] = base_url
        response = litellm.completion(**params)
        provider_label = PROVIDERS.get(provider, {}).get("label", provider)
        return ConnectionTestResponse(
            success=True,
            message=f"连接成功 - {provider_label}",
            model_info={"model": response.model, "usage": dict(response.usage) if response.usage else None},
        )
    except Exception as e:
        return ConnectionTestResponse(success=False, message=f"连接失败: {e}")
