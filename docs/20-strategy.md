# 策略管理 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 20 |
| 模块名称 | 策略管理 |
| 核心功能 | 用户自定义分析策略（模板 CRUD、权重配置、Prompt 管理） |
| 关键文件 | `backend/app/services/strategy.py` |
| 触发方式 | REST API |

## 2. 功能详情

### 2.1 策略模板类型

| 类型 | 说明 |
|---|---|
| comprehensive | 综合个股分析 |
| sector | 板块分析 |
| market | 大盘分析 |
| review | 复盘 |
| recommendation | 推荐 |

### 2.2 策略配置

| 配置项 | 说明 |
|---|---|
| name | 策略名称 |
| type | 策略类型 |
| dimension_weights | 各维度权重配置 |
| prompt_template | Prompt 模板 |
| enabled | 是否启用 |

### 2.3 Prompt 模板变量

- `{{stock_code}}` — 股票代码
- `{{stock_name}}` — 股票名称
- `{{trade_date}}` — 交易日期
- `{{dimensions}}` — 维度数据

## 3. API 端点

- `GET /api/v1/strategy` — 策略列表
- `POST /api/v1/strategy` — 创建策略
- `PUT /api/v1/strategy/{id}` — 更新策略
- `DELETE /api/v1/strategy/{id}` — 删除策略
- `GET /api/v1/strategy/{id}` — 获取策略详情

## 4. 前端页面

- `/strategy` — 策略管理页面
