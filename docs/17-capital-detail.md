# 资金流明细 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 17 |
| 模块名称 | 资金流明细 |
| 核心功能 | 北向资金（港资持股）、融资融券数据 |
| 关键文件 | `backend/app/services/capital_detail.py` |
| 触发方式 | 定时任务 |

## 2. 数据类型

### 2.1 北向资金（港资）

| 字段 | 说明 |
|---|---|
| stock_code | 股票代码 |
| stock_name | 股票名称 |
| holding_shares | 持股数量 |
| holding_value | 持股市值 |
| holding_ratio | 持股占比 |
| change_shares | 持股变动 |
| change_ratio | 变动比例 |

### 2.2 融资融券

| 字段 | 说明 |
|---|---|
| stock_code | 股票代码 |
| margin_balance | 融资余额 |
| margin_buy | 融资买入额 |
| short_balance | 融券余额 |
| short_sell | 融券卖出量 |

## 3. 数据来源

- 东方财富 HGT/HST 数据接口
- akshare 融资融券接口

## 4. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `stock_capital_detail_snapshot` | 16:40（工作日） | 个股资金流明细快照 |

## 5. 数据表

- `stock_hk_holding` — 港资持股表
- `stock_margin` — 融资融券表
