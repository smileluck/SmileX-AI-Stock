<!-- last-updated: 2026-06-05 -->
# 项目定位与技术栈

## 项目定位

SmileX AI Stock — AI 驱动的 A 股市场分析平台。提供实时大盘行情、多源新闻聚合、板块资金流向、AI 市场分析与预测、AI 对话助手等功能。

## 后端技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.13+ |
| Web 框架 | FastAPI |
| ASGI 服务器 | Uvicorn |
| 数据库 | SQLite（原生 SQL，无 ORM） |
| 数据获取 | AKShare（主要）+ 东方财富 HTTP API（补充） |
| LLM 调用 | OpenAI SDK → LiteLLM Proxy |
| 定时任务 | APScheduler |
| 包管理 | uv |

## 前端技术栈

| 类别 | 技术 |
|------|------|
| 框架 | React 19 |
| 构建工具 | Vite 8 |
| 语言 | TypeScript 6 |
| UI 库 | Ant Design 6 |
| 图表 | ECharts 6 + echarts-for-react |
| HTTP 客户端 | Axios |
| 路由 | React Router DOM 7 |
| 包管理 | npm |

## LLM 代理层

| 类别 | 技术 |
|------|------|
| 代理 | LiteLLM Proxy |
| 配置 | `llm_proxy/config.yaml` |

## 核心特性

| 特性 | 说明 |
|------|------|
| 多源新闻聚合 | 15+ 数据源（东方财富、财联社、同花顺、新浪等），统一 `BaseSource` 抽象 |
| 大盘行情 | 实时 A 股指数 + 全球指数，东方财富 API 直连 |
| 板块快照 | 行业/概念板块每日快照，含资金流向数据 |
| AI 市场分析 | 每日自动分析 + 预测 + 复盘，支持多模型切换 |
| AI 对话 | 通过 LiteLLM 代理转发，OpenAI 兼容接口 |
| 定时任务 | 新闻同步（5 分钟）、分析生成（收盘后）、板块快照（收盘后） |
