# SmileX A股量化选股系统

基于 Python 的 A 股量化选股辅助工具，支持技术指标分析、策略回测、每日选股扫描和多源资讯查询。

## 功能

- **大盘概览** — 上证/深证/创业板指数走势，涨跌家数统计
- **每日选股** — 全市场扫描，多指标评分筛选推荐股票
- **个股分析** — K 线图 + MA/MACD/RSI/布林带等指标叠加展示
- **策略回测** — 双均线交叉策略回测，输出年化收益/最大回撤/夏普比率
- **历史推荐** — 过往推荐记录追踪
- **资讯查询** — 同花顺（板块/评级）、东方财富（资金流向/北向资金/龙虎榜）、雪球（热度排行）三站聚合
- **系统设置** — 定时任务启停、扫描时间配置、手动触发、通知记录查看

## 技术栈

Python 3.12+ / AKShare / Backtrader / Streamlit / SQLite / pandas-ta / Plotly

## 快速开始

### 环境准备

需要先安装 [uv](https://docs.astral.sh/uv/) 包管理工具：

```bash
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 安装依赖

```bash
uv sync
```

### 一键启动

```bash
uv run python main.py
```

启动后浏览器访问 http://localhost:8501，在看板「系统设置」页面中：
- 配置每日扫描时间（时/分），启动或停止定时任务
- 手动触发一次选股扫描
- 查看扫描历史和通知记录

按 `Ctrl+C` 退出所有服务。

## 项目结构

```
├── smilex/                     # 核心包
│   ├── config.py               # 全局配置
│   ├── fetcher.py              # 数据采集（AKShare）
│   ├── store.py                # 数据存储（SQLite）
│   ├── indicators.py           # 技术指标计算
│   ├── strategy.py             # 交易策略
│   ├── backtest.py             # 回测引擎
│   ├── scanner.py              # 每日选股扫描器
│   ├── notify.py               # 通知推送
│   ├── scheduler.py            # 调度服务
│   └── consult/                # 资讯查询（同花顺/东财/雪球）
├── dashboard/
│   ├── app.py                  # Streamlit 主入口
│   └── pages/                  # 七个功能页面
├── main.py                     # 一键启动入口
├── pyproject.toml              # 项目依赖
└── uv.lock                    # 锁文件
```

## 选股扫描逻辑

每日收盘后全市场扫描，评分筛选：

1. 过滤 ST、停牌、涨跌停股票
2. 均线多头排列（MA5 > MA10 > MA20 > MA60）— 30 分
3. MACD 金叉 — 20 分
4. 量比 > 1.5（放量）— 20 分
5. 收盘价站上布林带中轨 — 15 分
6. RSI 适中区间（40-70）— 15 分

按总分排序输出推荐列表。

## 免责声明

本项目仅供学习研究，不构成任何投资建议。股市有风险，投资需谨慎。
