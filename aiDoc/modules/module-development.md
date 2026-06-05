<!-- last-updated: 2026-06-05 -->
# 模块开发指南

## 新建后端模块

以添加一个新的功能模块为例（如"个股分析"）：

### 1. 创建目录结构

不需要创建新目录，在现有 `app/` 结构中添加文件即可。

### 2. 定义 Model

在 `app/models/market.py`（或新建文件）中添加 Pydantic 模型：

```python
from pydantic import BaseModel

class StockItem(BaseModel):
    code: str
    name: str
    price: float | None = None

class StockOverviewResponse(BaseModel):
    items: list[StockItem]
    fetch_time: str
```

### 3. 实现 Service

在 `app/services/` 下新建文件（如 `stock.py`）：

```python
import akshare as ak
from datetime import datetime

def get_stock_overview(code: str) -> dict:
    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
    return {
        "items": df.tail(10).to_dict("records"),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
```

### 4. 创建 API Endpoint

在 `app/api/` 下新建文件（如 `stock.py`）：

```python
from fastapi import APIRouter, Query
from app.models.market import StockOverviewResponse
from app.services.stock import get_stock_overview

router = APIRouter(tags=["stock"])

@router.get("/stock/overview", response_model=StockOverviewResponse)
def stock_overview(code: str = Query(..., description="股票代码")):
    return get_stock_overview(code)
```

### 5. 注册 Router

在 `app/main.py` 中导入并注册：

```python
from app.api.stock import router as stock_router
app.include_router(stock_router, prefix="/api/v1")
```

### 6. 如需数据库表

在 `app/database.py` 的 `_SCHEMA` 中添加 `CREATE TABLE IF NOT EXISTS ...`。

## 新建前端功能

### 1. 定义类型

在 `src/types/index.ts` 中添加接口定义，与后端 Model 对齐。

### 2. 封装 API

在 `src/api/` 下新建文件（如 `stock.ts`）：

```typescript
import client from "./client";
import type { StockOverviewResponse } from "../types";

export async function fetchStockOverview(code: string): Promise<StockOverviewResponse> {
  const { data } = await client.get("/stock/overview", { params: { code } });
  return data;
}
```

### 3. 创建页面

在 `src/pages/` 下新建文件（如 `StockAnalysis.tsx`），使用 Ant Design 组件和 ECharts 图表。

### 4. 添加路由

在 `src/App.tsx` 中添加 `<Route>` 条目。

### 5. 添加菜单

在 `src/components/Layout/Sidebar.tsx` 的 `menuItems` 中添加导航项。

## 设计原则

- 自包含：新功能文件放在对应层目录下，不跨层
- 遵循现有模式：参考 `market` 或 `sector` 模块的结构
- 优先使用 akshare：数据获取优先使用 akshare，参考 `akshare-docs/`

## 参考文件

- 后端完整示例：`app/api/market.py` → `app/services/market.py` → `app/models/market.py`
- 前端完整示例：`src/api/market.ts` → `src/pages/Dashboard.tsx` → `src/types/index.ts`
