# 回测引擎 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 21 |
| 模块名称 | 回测引擎 |
| 核心功能 | A股规则撮合（T+1/最小100股/佣金/印花税）、每日信号生成、交割单记录 |
| 关键文件 | `backend/app/services/backtest/` |
| 触发方式 | REST API + 前端页面 |

## 2. 子模块

### 2.1 engine.py — 撮合引擎

**交易规则（A股）**：

| 规则 | 说明 |
|---|---|
| T+1 | 当日买入，次日才能卖出 |
| 最小交易单位 | 100 股（1手） |
| 佣金 | 双边万 2.5（买卖均收） |
| 印花税 | 卖方千 1 |
| 涨跌停 | ±10%（ST ±5%） |

**撮合逻辑**：
-买入：按开盘价/收盘价撮合
- 卖出：按收盘价撮合
- 止损/止盈触发

### 2.2 strategies.py — 信号生成策略

| 策略 | 说明 |
|---|---|
| morning | 早盘策略 |
| midday | 午盘策略 |
| afternoon | 尾盘策略 |
| custom | 自定义因子策略 |

### 2.3 data_loader.py — 数据加载

- 从 `stock_daily` 表加载历史 K 线
- 支持时间范围筛选
- 支持股票池筛选

### 2.4 metrics.py — 绩效指标

| 指标 | 说明 |
|---|---|
| total_return | 总收益率 |
| annual_return | 年化收益率 |
| sharpe_ratio | 夏普比率 |
| max_drawdown | 最大回撤 |
| win_rate | 胜率 |
| profit_loss_ratio | 盈亏比 |
| trading_count | 交易次数 |

## 3. 输出内容

- 每日交易信号
- 持仓记录
- 交割单
- 绩效报表

## 4. API 端点

- `POST /api/v1/backtest` — 发起回测
- `GET /api/v1/backtest/{id}` — 回测结果
- `GET /api/v1/backtest/{id}/trades` — 交易明细
- `GET /api/v1/backtest/{id}/metrics` — 绩效指标

## 5. 前端页面

- `/backtest` — 回测页面
