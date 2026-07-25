# 个股 AI 分析 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 19 |
| 模块名称 | 个股 AI 分析 |
| 核心功能 | 五维度个股深度评分（基本面/技术面/消息面/资金面/情绪），输出综合评分/风险等级/操作建议 |
| 关键文件 | `backend/app/services/stock_analysis.py` |
| 触发方式 | REST API |

## 2. 五维度评分

| 维度 | 权重 | 评分因素 |
|---|---|---|
| 基本面 | 30% | 业绩、估值、成长性、财务健康度 |
| 技术面 | 25% | 趋势、形态、技术指标、量价关系 |
| 资金面 | 25% | 主力净流入、换手率、北向资金 |
| 消息面 | 10% | 利好/利空、题材热度、新闻影响 |
| 情绪面 | 10% | 板块联动、市场情绪、股吧热度 |

## 3. 输出内容

| 字段 | 说明 |
|---|---|
| stock_code | 股票代码 |
| stock_name | 股票名称 |
| overall_score | 综合评分（0-100） |
| risk_level | 风险等级（低/中/高） |
| operation_suggestion | 操作建议（买入/持有/观望/卖出） |
| dimension_scores | 各维度评分详情 |
| key_factors | 关键驱动因素 |
| risk_factors | 风险因素 |
| target_price | 目标价区间 |
| stop_loss | 止损价 |

## 4. API 端点

- `GET /api/v1/stock-analysis` — 个股 AI 分析

## 5. 前端页面

- `/stock/overview` — 个股分析总览
