# 定时调度器 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 25 |
| 模块名称 | 定时调度器 |
| 核心功能 | APScheduler BackgroundScheduler；支持 CronTrigger 和 IntervalTrigger；慢任务日志 |
| 关键文件 | `backend/app/services/scheduler.py` |
| 触发方式 | FastAPI 启动时自动注册 |

## 2. 配置参数

| 参数 | 值 | 说明 |
|---|---|---|
| `max_workers` | 8 | 最大并发任务数 |
| `misfire_grace_time` | 300 | 任务错失宽限时间（秒） |
| 慢任务阈值 | 30s | 超过此时间记录警告日志 |

## 3. 触发器类型

### 3.1 CronTrigger

按 cron 表达式触发，例如：
- `0 15 * * 1-5` — 每天 15:00（周一至周五）

### 3.2 IntervalTrigger

按固定间隔触发，例如：
- `seconds=300` — 每 5 分钟

## 4. 定时任务总览（26 个）

| 时间 | 任务 ID | 功能 |
|---|---|---|
| 每 5 分钟 | `news_sync` | 新闻聚合抓取 |
| 09:26 | `stock_recommendation_morning` | 早盘 AI 个股推荐 |
| 09:30 | `watchlist_morning_analysis` | 自选股早盘 AI 分析 |
| 11:25 | `stock_recommendation_midday` | 午盘 AI 个股推荐 |
| 12:00 | `market_snapshot_midday` | 午间大盘快照 |
| 12:01 | `stock_daily_snapshot_midday` | 午间个股日线快照 |
| 12:02 | `sector_snapshot_midday` | 午间板块快照 |
| 12:03 | `limit_up_analysis_snapshot_midday` | 午间涨停/炸板采集 |
| 12:05 | `limit_up_ai_analysis_midday` | 午间涨停 AI 分析 |
| 14:45 | `stock_recommendation_afternoon` | 尾盘 AI 个股推荐 |
| 15:00 | `limit_up_analysis_snapshot_close` | 收盘涨停/炸板采集 |
| 15:05 | `limit_up_ai_analysis_close` | 收盘涨停 AI 分析 |
| 15:10 | `market_snapshot_close` | 收盘大盘快照 |
| 15:12 | `stock_daily_snapshot_close` | 收盘个股日线快照 |
| 15:15 | `daily_market_analysis` | 指数分析 + 次日预测 |
| 15:20 | `sector_snapshot_close` | 收盘板块快照 |
| 15:25 | `ai_daily_report` | AI 综合收盘报告 |
| 15:30 | `watchlist_daily_snapshot` | 自选股收盘快照 |
| 15:30 | `limit_up_snapshot` | 涨停股快照 |
| 15:35 | `stock_recommendation_review` | 收盘复盘推荐 |
| 15:42 | `watchlist_close_analysis` | 自选股收盘 AI 分析 |
| 15:50 | `tomorrow_strategy_generation` | 明日策略生成 |
| 15:58 | `sector_ai_analysis` | 板块 AI 分析 |
| 16:00 | `research_sync` | 券商研报抓取 |
| 16:10 | `research_pick_generation` | 研报 AI 选股 |
| 16:30 | `stock_fundamental_snapshot` | 个股基本面快照 |
| 16:40 | `stock_capital_detail_snapshot` | 个股资金流明细快照 |
| 17:00 | `sync_log_cleanup` | 清理 90 天前 sync_log |
| 周日 21:00 | `sector_ai_analysis_sunday` | 周日板块 AI 分析 |

## 5. 调度策略优化

收盘时段（15:00-15:58）已错峰：LLM 重任务（15:05/15:15/15:25/15:35/15:42/15:50/15:58）彼此间隔 ≥ 7 分钟，避免 4 worker 池饱和导致假死。

## 6. 前端页面

- `/scheduler` — 定时任务管理
