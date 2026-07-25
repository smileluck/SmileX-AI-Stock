# 历史数据回填 PRD

## 1. 模块概述

| 属性 | 值 |
|---|---|
| 模块 ID | 22 |
| 模块名称 | 历史数据回填 |
| 核心功能 | 补全 stock_daily 历史 K 线（自选股池或全市场） |
| 关键文件 | `backend/app/services/backfill_daily.py` |
| 触发方式 | 命令行手动触发 |

## 2. 使用方式

```bash
# 回填全市场历史数据
python -m app.services.backfill_daily --all

# 回填指定股票
python -m app.services.backfill_daily --codes 600519,000001

# 回填自选股池
python -m app.services.backfill_daily --watchlist

# 指定日期范围
python -m app.services.backfill_daily --all --start 2024-01-01 --end 2024-12-31
```

## 3. 参数说明

| 参数 | 说明 |
|---|---|
| `--all` | 回填全市场 |
| `--codes` | 指定股票代码（逗号分隔） |
| `--watchlist` | 回填自选股池 |
| `--start` | 开始日期 |
| `--end` | 结束日期 |
| `--force` | 强制覆盖已有数据 |

## 4. 数据来源

- 东方财富 daily K 线接口
- akshare 行情接口
