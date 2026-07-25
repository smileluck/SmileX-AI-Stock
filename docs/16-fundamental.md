# 基本面数据 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 16 |
| 模块名称 | 基本面数据 |
| 核心功能 | 个股财务指标快照（EPS/ROE/营收增长率/净利润增长率/毛利率/净利率） |
| 关键文件 | `backend/app/services/fundamental.py` |
| 触发方式 | 定时任务 |

## 2. 数据字段

| 字段 | 说明 |
|---|---|
| eps | 每股收益 |
| roe | 净资产收益率 |
| revenue_growth | 营收增长率 |
| net_profit_growth | 净利润增长率 |
| gross_margin | 毛利率 |
| net_margin | 净利率 |
| debt_ratio | 资产负债率 |
| pe | 市盈率 |
| pb | 市净率 |
| market_cap | 总市值 |

## 3. 数据来源

- 东方财富 financial data API
- akshare 财务数据接口

## 4. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `stock_fundamental_snapshot` | 16:30（工作日） | 个股基本面快照 |

## 5. 数据表

- `stock_fundamental` — 基本面数据表

## 6. 调用方

- `stock_analysis.py` — 个股 AI 分析
