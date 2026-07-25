# 自选股管理 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 10 |
| 模块名称 | 自选股管理 |
| 核心功能 | 自选股 CRUD、买入时机分析、早盘/收盘 AI 买点分析 |
| 关键文件 | `backend/app/services/watchlist.py`, `watchlist_analysis.py`, `watchlist_snapshot.py` |
| 触发方式 | 定时任务 + REST API |

## 2. 子模块

### 2.1 watchlist.py — 自选股 CRUD

| 功能 | 说明 |
|---|---|
| 添加自选股 | 按股票代码添加 |
| 删除自选股 | 按股票代码删除 |
| 批量导入 | 支持 CSV 导入 |
| 分组管理 | 按行业/题材分组 |
| 状态管理 | 关注/持仓/卖出等状态 |

### 2.2 watchlist_snapshot.py — 每日快照

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `watchlist_daily_snapshot` | 15:30（工作日） | 自选股收盘快照 |

快照数据：OHLCV + 资金流

### 2.3 watchlist_analysis.py — AI 分析

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `watchlist_morning_analysis` | 09:30（工作日） | 自选股早盘AI分析 |
| `watchlist_close_analysis` | 15:42（工作日） | 自选股收盘AI分析 |

分析内容：
- 买点分析（buy/wait/avoid）
- 持仓建议
- 风险提示

## 3. API 端点

- `GET /api/v1/watchlist` — 自选股列表
- `POST /api/v1/watchlist` — 添加自选股
- `DELETE /api/v1/watchlist/{code}` — 删除自选股
- `GET /api/v1/watchlist/analysis` — AI 分析结果

## 4. 前端页面

- `/watchlist/stocks` — 自选股列表
- `/watchlist/stock/{code}` — 自选股详情
- `/watchlist/sectors` — 自选板块
