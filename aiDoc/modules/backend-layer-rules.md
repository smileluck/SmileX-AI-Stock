<!-- last-updated: 2026-06-05 -->
# 后端分层约束

## 总原则

严格分层，不跨层调用。Router 只调用 Service，Service 调用数据源/数据库/LLM，Router 不直接操作数据库。

## Model 层

- 位置：`backend/app/models/*.py`
- 使用 Pydantic `BaseModel` 定义
- 每个 API 响应对应一个 `*Response` 模型
- 字段使用 Python 类型注解（`str | None`、`list[dict]`）
- 实际文件：`app/models/market.py`、`app/models/news.py`

命名规则：
- 请求模型：`*Request`（如 `ChatRequest`、`GenerateAnalysisRequest`）
- 响应模型：`*Response`（如 `MarketOverviewResponse`、`NewsResponse`）
- 列表项：`*Item`（如 `IndexItem`、`SectorItem`）

## Service 层

- 位置：`backend/app/services/*.py`
- 纯函数式设计，不使用类
- 函数返回 `dict`（由 Router 层的 `response_model` 自动序列化）
- 日志使用 `logging.getLogger(__name__)`
- 数据库操作：`get_connection()` 获取连接，`try/finally` 确保关闭

实际文件：
- `app/services/market.py` — 大盘行情（东方财富 API + akshare）
- `app/services/sector.py` — 板块快照与历史查询
- `app/services/news_sync.py` — 新闻同步与查询
- `app/services/market_analysis.py` — AI 分析生成
- `app/services/llm.py` — LLM 调用封装
- `app/services/scheduler.py` — 定时任务管理
- `app/services/news_fetcher.py` — 数据源注册表

## Router (API Endpoint) 层

- 位置：`backend/app/api/*.py`
- 使用 `APIRouter` 创建路由
- 通过 `response_model` 参数指定响应类型
- 参数提取使用 `Query()`、Pydantic `BaseModel` 请求体
- 不包含业务逻辑，只做参数校验和调用 Service

实际文件：
- `app/api/market.py` — 大盘与板块接口（prefix: 无，tags: market）
- `app/api/news.py` — 新闻接口（tags: news）
- `app/api/chat.py` — AI 对话接口（prefix: /ai，tags: ai）
- `app/api/proxy.py` — LLM 代理状态（prefix: /ai，tags: ai）
- `app/api/market_analysis.py` — 市场分析接口（tags: market_analysis）

## 新闻源层

- 位置：`backend/sources/*.py`
- 必须继承 `sources.base.BaseSource`
- 实现 `fetch()` 方法，返回 `pd.DataFrame`
- DataFrame 必须包含列：`source, title, content, url, publish_time, fetch_time, extra`
- 通过 `SOURCE_REGISTRY` 字典注册

## 数据库层

- 位置：`backend/app/database.py`
- SQLite，无 ORM，使用原生 SQL
- 连接使用 `get_connection()`，设置 `row_factory = sqlite3.Row`
- Schema 在 `_SCHEMA` 常量中定义，`init_db()` 执行建表
- 表名：`news`、`sync_log`、`market_analysis`、`sector_snapshot`、`sector_snapshot_item`
