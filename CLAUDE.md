# SmileX AI Stock

A股智能分析系统，基于 FastAPI + React + LiteLLM。

## 架构

- **后端**: `backend/` — FastAPI, SQLite, APScheduler
- **前端**: `frontend/` — React + Vite + Ant Design
- **LLM 代理**: `llm_proxy/` — LiteLLM Proxy，统一管理多个模型

## LLM 模型路由

通过 `llm_proxy/config.yaml` 配置，后端通过以下环境变量选择模型：

| 环境变量 | 默认值 | 用途 |
|----------|--------|------|
| `MODEL_ANALYSIS` | `analysis` | 每日分析、收盘报告、复盘 |
| `MODEL_NEWS_SCORER` | `news-scorer` | 新闻影响力评分筛选 |
| `MODEL_CHAT` | `MiniMax-M3` | 用户对话 |

修改 `config.yaml` 中对应 `model_name` 的 `litellm_params.model` 即可切换底层模型。

## 后端模型调用规范

- `llm.analysis_chat(messages)` — 市场分析、预测、复盘
- `llm.score_news(messages)` — 新闻影响力评分
- `llm.chat(messages)` — 通用对话（使用 MODEL_CHAT）

不要直接传入 model 参数，使用上述封装函数。

## 定时任务

在 `backend/app/main.py` 的 `lifespan` 中注册，使用 APScheduler cron 表达式：

| 任务 | 时间 | 说明 |
|------|------|------|
| `news_sync` | 每 5 分钟 | 从 14 个新闻源抓取 |
| `daily_market_analysis` | 工作日 15:15 | 指数分析 + 次日预测 |
| `sector_snapshot` | 工作日 15:20 | 板块快照 + 资金流 |
| `ai_daily_report` | 工作日 15:25 | AI 综合收盘报告 |
| `limit_up_snapshot` | 工作日 15:30 | 涨停股快照 |
| `stock_recommendation` | 工作日 15:35 | AI 个股推荐生成 |

## 数据库

SQLite，位于 `backend/data/stock.db`。Schema 定义在 `backend/app/database.py`，`init_db()` 自动建表和迁移。

## 新闻源

14 个源定义在 `backend/app/services/news_fetcher.py` 的 `SOURCE_REGISTRY`，每个源继承 `sources/base.py:BaseSource`。

## 前端路由

- `/market` — 大盘总览
- `/market/analysis` — AI 每日分析（含"每日分析和预测" + "收盘分析"两个 Tab）
- `/market/history` — 历史行情
- `/sector/today` — 板块总览
- `/sector/history` — 板块历史
- `/stock/overview` — 个股分析总览
- `/stock/limit-up` — 今日涨停
- `/stock/recommendation` — AI 个股推荐
- `/stock/history` — 历史推荐
- `/news` — 新闻聚合
- `/scheduler` — 定时任务管理
- `/ai-assistant/llm-config` — LLM 配置
- `/ai-assistant/chat` — AI 对话
