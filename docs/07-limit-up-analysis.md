# 涨停/炸板分析 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 07 |
| 模块名称 | 涨停/炸板分析 |
| 核心功能 | 涨停股池、炸板股池、涨停原因、连板数；午盘/收盘两档 AI 分析报告 |
| 关键文件 | `backend/app/services/limit_up_analysis.py` |
| 触发方式 | 定时任务 + REST API |

## 2. 功能详情

### 2.1 涨停股池

| 字段 | 说明 |
|---|---|
| stock_code | 股票代码 |
| stock_name | 股票名称 |
| close_price | 涨停价 |
| change_pct | 涨幅 |
| limit_up_days | 连板数 |
| seal_amount | 封板资金 |
| first_seal_time | 首次封板时间 |
| reason | 涨停原因 |

### 2.2 炸板股池

- 曾涨停但未封住的股票
- 炸板时间、炸板幅度

### 2.3 AI 分析报告

- 涨停股特征分析
- 炸板股风险提示
- 明日涨停预测

## 3. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `limit_up_analysis_snapshot_midday` | 12:03（工作日） | 午间涨停/炸板数据采集 |
| `limit_up_ai_analysis_midday` | 12:05（工作日） | 午间涨停AI分析 |
| `limit_up_analysis_snapshot_close` | 15:00（工作日） | 收盘涨停/炸板数据采集 |
| `limit_up_ai_analysis_close` | 15:05（工作日） | 收盘涨停AI分析 |
| `limit_up_snapshot` | 15:30（工作日） | 涨停股快照 |

## 4. API 端点

- `GET /api/v1/limit-up-analysis` — 涨停分析
- `GET /api/v1/limit-up-analysis/list` — 涨停股列表

## 5. 前端页面

- `/stock/limit-up` — 今日涨停
