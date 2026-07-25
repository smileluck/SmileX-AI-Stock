# 技术指标计算 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 18 |
| 模块名称 | 技术指标计算 |
| 核心功能 | MA/MACD/RSI/KDJ/布林带计算引擎 |
| 关键文件 | `backend/app/services/technical_indicators.py` |
| 触发方式 | 被其他模块调用 |

## 2. 指标详情

### 2.1 均线（MA）

| 指标 | 参数 |
|---|---|
| MA5 | 5日均线 |
| MA10 | 10日均线 |
| MA20 | 20日均线 |
| MA60 | 60日均线 |

### 2.2 MACD

| 指标 | 说明 |
|---|---|
| DIF | 快线（12日EMA - 26日EMA） |
| DEA | 慢线（DIF的9日EMA） |
| MACD_BAR | 柱状图（DIF - DEA）× 2 |

### 2.3 RSI

| 指标 | 参数 |
|---|---|
| RSI6 | 6日RSI |
| RSI12 | 12日RSI |
| RSI24 | 24日RSI |

### 2.4 KDJ

| 指标 | 说明 |
|---|---|
| K | 随机指标K值 |
| D | 随机指标D值 |
| J | 随机指标J值 |

### 2.5 布林带（Bollinger Bands）

| 指标 | 参数 |
|---|---|
| upper | 上轨（20日MA + 2倍标准差） |
| middle | 中轨（20日MA） |
| lower | 下轨（20日MA - 2倍标准差） |

## 3. 调用方

- `stock_analysis.py` — 个股 AI 分析
- `stock.py` — AI 个股推荐
