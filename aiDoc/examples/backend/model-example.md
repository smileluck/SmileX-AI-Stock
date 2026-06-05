<!-- last-updated: 2026-06-05 -->
# Model 层示例

## 用途

展示 Pydantic BaseModel 的定义方式，包括嵌套模型和可空字段处理。

## 核心原则

- 每个 API 响应对应一个 Response 模型
- 列表项使用独立的 Item 模型
- 可空字段使用 `| None = None`

## 示例

```python
from pydantic import BaseModel


class IndexItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    amount: float | None = None


class MarketOverviewResponse(BaseModel):
    cn_main: list[IndexItem]
    international: list[IndexItem]
    fetch_time: str
```

## 关键点

- 字段类型使用 Python 3.13+ 语法（`float | None` 而非 `Optional[float]`）
- 列表使用 `list[Type]` 而非 `List[Type]`
- 时间字段统一使用 `str` 类型
- `fetch_time` 作为元数据字段附加在响应模型顶层

## 真实参考文件

- `app/models/market.py` — 大盘和板块相关模型（约 200 行）
- `app/models/news.py` — 新闻相关模型（约 50 行）
