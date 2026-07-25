# LLM 调用代理 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 23 |
| 模块名称 | LLM 调用代理 |
| 核心功能 | 统一封装 LLM 调用（分析/新闻评分/闲聊/研报选股）；Semaphore 并发控制；JSON 解析；模型路由 |
| 关键文件 | `backend/app/services/llm.py` |
| 触发方式 | 被所有 AI 分析服务内部调用 |

## 2. 函数封装

| 函数 | 模型 | 用途 |
|---|---|---|
| `llm.analysis_chat(messages)` | MODEL_ANALYSIS | 市场分析、预测、复盘 |
| `llm.score_news(messages)` | MODEL_NEWS_SCORER | 新闻影响力评分 |
| `llm.chat(messages)` | MODEL_CHAT | 通用对话 |
| `llm.research_pick_chat(messages)` | MODEL_ANALYSIS | 研报选股分析 |

## 3. 模型路由

环境变量配置：

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `MODEL_ANALYSIS` | `analysis` | 每日分析、收盘报告、复盘 |
| `MODEL_NEWS_SCORER` | `news-scorer` | 新闻影响力评分筛选 |
| `MODEL_CHAT` | `MiniMax-M3` | 用户对话 |

优先级：数据库配置 > 环境变量

## 4. 并发控制

- Semaphore 并发限制：`max=CONCURRENCY`（默认 4）
- 1 小时客户端重建（避免 token 累积）

## 5. JSON 解析

- 支持 ` ```json ... ``` ` 包裹格式
- 支持裸 JSON
- 失败时自动重试
