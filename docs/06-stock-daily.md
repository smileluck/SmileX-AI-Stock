# 个股日线数据 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 06 |
| 模块名称 | 个股日线数据 |
| 核心功能 | 全市场个股日线行情（OHLCV）、排行榜、多维度排序查询 |
| 关键文件 | `backend/app/services/stock_daily.py` |
| 触发方式 | 定时任务 + REST API |

## 2. 功能详情

### 2.1 数据字段

| 字段 | 说明 |
|---|---|
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| amount | 成交额 |
| change_pct | 涨跌幅 |
| turnover | 换手率 |
| pe | 市盈率 |
| pb | 市净率 |
| market_cap | 总市值 |

### 2.2 排序维度

- 涨幅（从小到大）
- 涨幅（从大到小）
- 换手率
- 主力净流入
- 成交额
- 市值

### 2.3 API 端点

- `GET /api/v1/stock-daily` — 个股日线列表
- `GET /api/v1/stock-daily/rankings` — 排行榜

## 3. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `stock_daily_snapshot_midday` | 12:01（工作日） | 午间个股日线快照 |
| `stock_daily_snapshot_close` | 15:12（工作日） | 收盘个股日线快照 |

## 4. 数据表

- `stock_daily` — 个股日线表

## 5. 前端页面

- `/stock/overview` — 个股分析总览
