# SmileX A股量化选股系统

基于 Python 的 A 股量化选股辅助工具，支持技术指标分析、策略回测、每日选股扫描和多源资讯查询。

## 功能

- **大盘概览** — 上证/深证/创业板指数走势，涨跌家数统计
- **每日选股** — 全市场扫描，多指标评分筛选推荐股票
- **个股分析** — K 线图 + MA/MACD/RSI/布林带等指标叠加展示
- **策略回测** — 双均线交叉策略回测，输出年化收益/最大回撤/胜率
- **历史推荐** — 过往推荐记录追踪与回看
- **资讯查询** — 同花顺（板块/评级）、东方财富（资金流向/北向资金/龙虎榜）、雪球（热度排行）三站聚合
- **系统设置** — 定时任务启停、扫描时间配置、手动触发、通知记录查看

## 快速开始

### 安装

```bash
# 安装 uv（如未安装）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装依赖
uv sync
```

### 启动

```bash
uv run python main.py
```

浏览器打开 http://localhost:8501，在看板「系统设置」页面中控制定时任务和手动扫描。

按 `Ctrl+C` 退出。

## 项目结构

```
SmileX-AI-Stock/
├── smilex/                     # 核心包
│   ├── config.py               # 全局配置
│   ├── fetcher.py              # 数据采集（AKShare）
│   ├── store.py                # 数据存储（SQLite）
│   ├── indicators.py           # 技术指标（MA/MACD/RSI/布林带/KDJ/量比）
│   ├── strategy.py             # 交易策略（双均线交叉）
│   ├── backtest.py             # 回测引擎（Backtrader）
│   ├── scanner.py              # 每日选股扫描器
│   ├── notify.py               # 通知推送
│   ├── scheduler.py            # 调度服务（APScheduler）
│   └── consult/                # 资讯查询
│       ├── ths.py              #   同花顺（板块/评级）
│       ├── em.py               #   东方财富（资金/北向/龙虎榜/融资融券）
│       └── xq.py               #   雪球（热度排行）
├── dashboard/
│   ├── app.py                  # Streamlit 主入口
│   └── pages/                  # 七个功能页面
│       ├── 01_大盘概览.py
│       ├── 02_今日推荐.py
│       ├── 03_个股分析.py
│       ├── 04_策略回测.py
│       ├── 05_历史推荐.py
│       ├── 06_系统设置.py
│       └── 07_资讯查询.py
├── main.py                     # 一键启动入口
├── pyproject.toml
└── uv.lock
```

## 选股逻辑

全市场扫描，多条件评分筛选：

| 条件 | 分值 |
|------|------|
| 均线多头排列（MA5 > MA10 > MA20 > MA60） | 30 |
| MACD 金叉 | 20 |
| 量比 > 1.5（放量） | 20 |
| 收盘价站上布林带中轨 | 15 |
| RSI 适中区间（40-70） | 15 |

过滤规则：排除 ST、停牌、上市不足 60 天、涨跌停股票。

## 技术栈

Python 3.12+ / AKShare / Backtrader / Streamlit / SQLite / pandas-ta / Plotly / APScheduler

## 免责声明

本项目仅供学习研究，不构成任何投资建议。股市有风险，投资需谨慎。
