# 新闻-板块关联 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 15 |
| 模块名称 | 新闻-板块关联 |
| 核心功能 | LLM 打分每条新闻对各板块的影响（0-10分） |
| 关键文件 | `backend/app/services/news_sector_assoc.py` |
| 触发方式 | 被其他模块调用 |

## 2. 功能详情

### 2.1 输入

- 指定交易日期的 top_n 条新闻
- 当日板块快照（行业 + 概念）

### 2.2 处理流程

```
1. 获取新闻列表
2. 获取当日板块快照
3. 调用 LLM（news_scorer）批量评估
4. 解析 LLM 输出 JSON
5. 写入 news_sector_association 表
```

### 2.3 LLM 输出格式

```json
[
  {
    "news_index": 0,
    "sector_index": 1,
    "score": 8.5,
    "relevance": "high",
    "category": "政策利好"
  }
]
```

### 2.4 评分字段

| 字段 | 说明 |
|---|---|
| news_id | 新闻ID |
| sector_code | 板块代码 |
| sector_name | 板块名称 |
| sector_type | 板块类型（industry/concept） |
| impact_score | 影响评分（0-10） |
| impact_category | 影响类别（政策利好/业绩增长/行业景气/其他） |
| relevance | 相关性（high/medium/low） |
| trade_date | 交易日期 |

## 3. 调用方

- `market_analysis.py` — 大盘 AI 分析

## 4. 数据表

- `news_sector_association` — 新闻-板块关联表
