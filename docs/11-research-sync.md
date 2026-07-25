# 券商研报同步 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 11 |
| 模块名称 | 券商研报同步 |
| 核心功能 | 东方财富研报源抓取、入库、查询；支持机构/评级/行业过滤 |
| 关键文件 | `backend/app/services/research_sync.py`, `backend/sources/research_eastmoney.py` |
| 触发方式 | 定时任务 + REST API |

## 2. 数据源

| source | 说明 |
|---|---|
| `research_eastmoney` | 东方财富研报 |

## 3. 功能详情

### 3.1 采集方式

- API：`reportapi.eastmoney.com/report/list`
- page_size：100
- 支持分块采集（chunk_days=14）
- 分别抓取：
  - qType=0：个股研报
  - qType=1：行业研报

### 3.2 数据字段

| 字段 | 说明 |
|---|---|
| title | 研报标题 |
| url | 原文链接 |
| org | 机构名称 |
| analyst | 分析师 |
| rating | 评级（归一化） |
| target_price | 目标价 |
| current_price | 当前价 |
| industry | 行业 |
| stock_codes | 关联股票代码 |
| publish_date | 发布日期 |

### 3.3 评级归一化

| 原始评级 | 归一化 |
|---|---|
| 买入、强烈推荐、推荐 | 买入 |
| 增持、优大于市、谨慎推荐 | 增持 |
| 中性、持有、同步 | 中性 |
| 减持、回避、卖出、落后大势 | 减持 |

## 4. 定时任务

| 任务 ID | 时间 | 说明 |
|---|---|---|
| `research_sync` | 16:00（工作日） | 券商研报抓取 |

## 5. API 端点

- `GET /api/v1/research/reports` — 研报列表
- `GET /api/v1/research/reports/{id}` — 研报详情

## 6. 数据表

- `research_report` — 研报表
