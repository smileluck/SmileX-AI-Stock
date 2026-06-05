<!-- last-updated: 2026-06-05 -->
# Router 注册示例

## 用途

展示在 `app/main.py` 中注册路由的方式。

## 核心原则

- 所有路由统一挂载 `/api/v1` 前缀
- 每个 API 文件导出 `router`，在 `main.py` 中导入并注册
- 路由文件使用 `prefix` 参数添加子前缀

## 示例

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market import router as market_router
from app.api.news import router as news_router
from app.api.chat import router as chat_router

app = FastAPI(title="SmileX AI Stock", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
```

部分路由自带子前缀（在 API 文件中定义）：

```python
# app/api/chat.py
router = APIRouter(prefix="/ai", tags=["ai"])
# 实际路径: /api/v1/ai/chat
```

## 关键点

- CORS 只允许前端开发服务器 `http://localhost:5173`
- `prefix="/api/v1"` 全局统一
- 子前缀在 API 文件的 `APIRouter(prefix=...)` 中声明

## 真实参考文件

- `app/main.py` — 完整路由注册和生命周期管理
