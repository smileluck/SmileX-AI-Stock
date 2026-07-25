# 研报 AI 选股 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 12 |
| 模块名称 | 研报 AI 选股 |
| 核心功能 | 规则初筛 → 多研报共识 → LLM 深度分析评分 |
| 关键文件 | `backend/app/services/research_pick.py` |
| 触发方式 | 定时任务 + REST API |

## 2. 筛选流程

### 2.1 第一阶段：规则初筛（90天内）

| 规则 | 条件 |
|---|---|
| 机构覆盖 | ≥ 3 家机构发布研报 |
| 评级 | ≥ 2 家给予"买入"评级 |
| 涨幅安全垫 | 60日涨幅 ≤ 30% |

### 2.2 第二阶段：多研报共识

- 按股票聚合研报
- 计算共识分（机构数 × 平均评级）
- 排序取 TOP

### 2.3 第三阶段：LLM 深度分析

- 对 TOP25 股票进行 LLM 分析
- 输出综合评分排序

## 3. 输出字段

| 字段 | 说明 |
|---|---|
| stock_code | 股票代码 |
| stock_name | 股票名称 |
| consensus_score | 共识分 |
| llm_score | LLM 综合评分 |
| rating_count | 研报数量 |
| avg_rating | 平均评级 |
| 60d_change | 60日涨幅 |
| target_price | 目标价 |
| reason | 推荐理由 |

## 4. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `research_pick_generation` | 16:10（工作日） | 研报AI选股 |

## 5. API 端点

- `GET /api/v1/research/picks` — 研报选股结果

## 6. 前端页面

- `/research-pick` — 研报AI选股（前端页面路径待确认）
