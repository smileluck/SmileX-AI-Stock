from pydantic import BaseModel

PROVIDERS = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"label": "Anthropic", "base_url": ""},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com"},
    "zhipu": {"label": "智谱AI", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
    "moonshot": {"label": "Moonshot", "base_url": "https://api.moonshot.cn/v1"},
    "minimax": {"label": "MiniMax", "base_url": "https://api.minimaxi.com/anthropic"},
    "kimi": {"label": "Kimi", "base_url": "https://api.kimi.com/coding/v1/chat/completions"},
}


class AIModelConfigCreate(BaseModel):
    name: str
    provider: str
    model: str
    base_url: str = ""
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 4096
    is_default: bool = False
    extra: dict = {}


class AIModelConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_default: bool | None = None
    is_enabled: bool | None = None
    extra: dict | None = None


class AIModelConfigResponse(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    base_url: str
    api_key_masked: str
    temperature: float
    max_tokens: int
    is_default: bool
    is_enabled: bool
    extra: dict
    created_at: str
    updated_at: str


class AIModelConfigListResponse(BaseModel):
    items: list[AIModelConfigResponse]
    total: int


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    model_info: dict | None = None


class ProviderInfo(BaseModel):
    id: str
    label: str
    base_url: str
