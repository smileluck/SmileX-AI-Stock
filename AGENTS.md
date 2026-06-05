# AGENTS.md

## akshare-docs 文档

`akshare-docs/` 目录包含 AKShare 库的完整离线文档，用于查阅可用的金融数据接口。开发新功能时请优先参考此目录中的文档。

### 文档目录结构

- `introduction.md` — AKShare 项目概述
- `installation.md` — 安装说明
- `tutorial.md` — 快速入门及接口列表
- `data_tips.md` — 数据使用注意事项
- `data/stock/` — 股票数据接口（行情、财务、板块等）
- `data/fund/` — 基金数据接口
- `data/futures/` — 期货数据接口
- `data/index/` — 指数数据接口
- `data/bond/` — 债券数据接口
- `data/currency/` — 汇率数据接口
- `data/energy/` — 能源数据接口

## 数据获取优先级

获取金融数据时，必须遵循以下优先级：

1. **优先使用 akshare** — 通过 `import akshare as ak` 调用对应接口获取数据。参考 `akshare-docs/` 中的文档查找合适的函数。
2. **仅在 akshare 无对应接口时**，才查找东方财富等 HTTP API 接口来同步数据。

### 现有 akshare 使用示例

项目中已有以下 akshare 用法可作参考：

```python
import akshare as ak

# 指数历史行情
df = ak.stock_zh_index_daily(symbol="sh000001")

# 同花顺行业板块指数
df = ak.stock_board_industry_index_ths(symbol="银行", start_date="20240101", end_date="20240601")

# 同花顺概念板块指数
df = ak.stock_board_concept_index_ths(symbol="人工智能", start_date="20240101", end_date="20240601")

# 全球财经新闻（同花顺）
df = ak.stock_info_global_ths()
```
