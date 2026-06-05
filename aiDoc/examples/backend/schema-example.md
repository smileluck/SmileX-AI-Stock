<!-- last-updated: 2026-06-05 -->
# Schema (请求体) 示例

## 用途

展示请求体 Pydantic 模型的定义方式。

## 核心原则

- 请求体使用独立 BaseModel
- 提供 `default` 默认值减少必填字段
- 响应模型包含 `success` + `message` 操作结果

## 示例

```python
from pydantic import BaseModel
from app.models.market import MarketAnalysisItem


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "MiniMax-M3"


class ChatResponse(BaseModel):
    content: str
    model: str


class GenerateAnalysisRequest(BaseModel):
    trade_date: str | None = None


class GenerateAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: MarketAnalysisItem | None = None
```

## 关键点

- `messages: list[dict]` — 复杂嵌套结构直接使用 dict 而非定义子模型
- `model: str = "MiniMax-M3"` — 带默认值的可选字段
- `data: MarketAnalysisItem | None = None` — 复用已有响应模型作为嵌套数据

## 真实参考文件

- `app/api/chat.py` — ChatRequest / ChatResponse
- `app/models/market.py` — GenerateAnalysisRequest / GenerateAnalysisResponse
