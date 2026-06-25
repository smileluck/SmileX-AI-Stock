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
| `stock_recommendation_morning` | 工作日 9:26 | 早盘AI个股推荐 |
| `watchlist_morning_analysis` | 工作日 9:30 | 自选股早盘AI分析 |
| `stock_recommendation_midday` | 工作日 11:25 | 午盘AI个股推荐 |
| `market_snapshot_midday` | 工作日 12:00 | 午间行情快照 |
| `stock_daily_snapshot_midday` | 工作日 12:01 | 午间个股日线快照 |
| `sector_snapshot_midday` | 工作日 12:02 | 午间板块快照 |
| `limit_up_analysis_snapshot_midday` | 工作日 12:03 | 午间涨停/炸板数据采集 |
| `limit_up_ai_analysis_midday` | 工作日 12:05 | 午间涨停AI分析 |
| `stock_recommendation_afternoon` | 工作日 14:45 | 尾盘AI个股推荐（主力净流入口径，非涨停） |
| `limit_up_analysis_snapshot_close` | 工作日 15:00 | 收盘涨停/炸板数据采集 |
| `limit_up_ai_analysis_close` | 工作日 15:05 | 收盘涨停AI分析 |
| `market_snapshot_close` | 工作日 15:10 | 收盘行情快照 |
| `stock_daily_snapshot_close` | 工作日 15:12 | 收盘个股日线快照 |
| `daily_market_analysis` | 工作日 15:15 | 指数分析 + 次日预测 |
| `sector_snapshot_close` | 工作日 15:20 | 收盘板块快照 |
| `ai_daily_report` | 工作日 15:25 | AI 综合收盘报告 |
| `limit_up_snapshot` | 工作日 15:30 | 涨停股快照 |
| `sector_prediction_review` | 工作日 15:30 | 板块预测复盘 |
| `watchlist_daily_snapshot` | 工作日 15:30 | 自选股收盘快照 |
| `stock_recommendation_review` | 工作日 15:35 | 收盘复盘推荐 |
| `watchlist_close_analysis` | 工作日 15:42 | 自选股收盘AI分析 |
| `tomorrow_strategy_generation` | 工作日 15:50 | 明日策略生成 |
| `sector_ai_analysis` | 工作日 15:58 | 板块AI分析 |
| `sector_ai_analysis_sunday` | 周日 21:00 | 板块AI分析 |
| `research_sync` | 工作日 16:00 | 券商研报抓取 |
| `research_pick_generation` | 工作日 16:10 | 研报AI选股 |
| `stock_fundamental_snapshot` | 工作日 16:30 | 个股基本面快照 |
| `stock_capital_detail_snapshot` | 工作日 16:40 | 个股资金流明细快照 |
| `sync_log_cleanup` | 每日 17:00 | 清理 90 天前的 sync_log |

> 收盘时段（15:00-15:58）已错峰：LLM 重任务（15:05/15:15/15:25/15:35/15:42/15:50/15:58）彼此间隔 ≥ 7 分钟，避免 4 worker 池饱和导致假死。scheduler 配置：`max_workers=8`，`misfire_grace_time=300`。

## 数据库

SQLite，位于 `backend/data/stock.db`。Schema 定义在 `backend/app/database.py`，`init_db()` 自动建表和迁移。

启用 WAL 模式 + `busy_timeout=30000ms` + `connect timeout=30s`，避免多线程并发写入时锁竞争导致假死。读写不互斥（写只锁 `-wal` 文件）。

## 新闻源

14 个源定义在 `backend/app/services/news_fetcher.py` 的 `SOURCE_REGISTRY`，每个源继承 `sources/base.py:BaseSource`。

## 前端路由

- `/market` — 大盘总览
- `/market/history` — 历史行情
- `/analysis/market` — 大盘AI分析（含"每日分析和预测" + "收盘分析"两个 Tab）
- `/analysis/sector` — 板块AI分析
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
