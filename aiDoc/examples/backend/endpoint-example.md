<!-- last-updated: 2026-06-05 -->
# Endpoint 层示例

## 用途

展示 FastAPI 路由函数的编写方式：参数提取、响应类型标注、调用 Service。

## 核心原则

- 使用 `APIRouter` 创建路由组
- 通过 `response_model` 指定响应类型
- Query 参数使用 `Query()` 声明约束
- 函数体只调用 Service，不含业务逻辑

## 示例

```python
from fastapi import APIRouter, Query

from app.models.market import MarketOverviewResponse, MarketHistoryResponse
from app.services.market import get_market_overview, get_market_history

router = APIRouter(tags=["market"])


@router.get("/market/overview", response_model=MarketOverviewResponse)
def market_overview():
    return get_market_overview()


@router.get("/market/history", response_model=MarketHistoryResponse)
def market_history(days: int = Query(default=30, le=365)):
    return get_market_history(days)
```

## 关键点

- `tags` 用于 Swagger UI 分组
- `Query(default=30, le=365)` — 默认值 + 上限约束
- `response_model` 确保 Swagger 文档正确，响应自动按模型过滤字段
- 无需手动序列化，直接返回 Service 的 dict

## 真实参考文件

- `app/api/market.py` — 大盘与板块的完整端点（约 85 行）
- `app/api/news.py` — 新闻聚合端点
