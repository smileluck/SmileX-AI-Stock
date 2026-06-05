<!-- last-updated: 2026-06-05 -->
# 系统架构与组件关系

## 根目录职责

| 目录 | 用途 |
|------|------|
| `backend/` | FastAPI 后端应用 |
| `frontend/` | React 前端应用 |
| `llm_proxy/` | LiteLLM 代理服务 |
| `akshare-docs/` | AKShare 离线文档 |
| `docs/` | 项目文档 |
| `graphify-out/` | 知识图谱输出 |

## 后端分层关系

```
Router (app/api/*.py)
  → Service (app/services/*.py)
    → 外部数据源 (akshare, 东方财富 API)
    → LLM (通过 app/services/llm.py → LiteLLM Proxy)
    → 数据库 (app/database.py → SQLite)
    → 新闻源 (sources/*.py → BaseSource)
```

### 各层职责

| 层 | 文件 | 职责 |
|----|------|------|
| Router | `app/api/*.py` | 参数提取、响应格式化、路由注册 |
| Service | `app/services/*.py` | 业务逻辑、数据获取与处理 |
| Model | `app/models/*.py` | Pydantic 请求/响应模型 |
| 数据源 | `sources/*.py` | 新闻抓取，继承 `BaseSource` |
| 数据库 | `app/database.py` | SQLite 表创建、连接管理 |
| 配置 | `app/config.py` | 环境变量、路径常量 |

## 核心基础设施

| 组件 | 位置 | 职责 |
|------|------|------|
| FastAPI App | `app/main.py` | 应用入口、路由注册、CORS、生命周期 |
| Scheduler | `app/services/scheduler.py` | APScheduler 封装，定时任务管理 |
| LLM Client | `app/services/llm.py` | OpenAI SDK 封装，通过 LiteLLM 代理调用 |
| Database | `app/database.py` | SQLite 建表、连接管理 |

## 前端数据流

```
API 封装 (src/api/*.ts)
  → 页面组件 (src/pages/*.tsx)
    → Ant Design 组件渲染
    → ECharts 图表渲染
```

### 前端结构

| 目录 | 职责 |
|------|------|
| `src/api/` | axios 请求封装，按模块拆分 |
| `src/pages/` | 页面级组件 |
| `src/components/` | 共享组件（Layout、Dashboard、News） |
| `src/types/` | TypeScript 类型定义，与后端 Model 对齐 |

## 模块对应关系

| 后端模块 | 前端页面 | API 文件 |
|----------|----------|----------|
| `api/market.py` | Dashboard, MarketHistory | `api/market.ts` |
| `api/news.py` | News | `api/news.ts` |
| `api/market_analysis.py` | MarketAnalysis | `api/marketAnalysis.ts` |
| `api/chat.py` | AIChat | `api/chat.ts` |
| `api/proxy.py` | LLMConfig | `api/aiConfig.ts` |
| `services/sector.py` | SectorOverview, SectorHistory | `api/sector.ts` |
| `services/scheduler.py` | Scheduler | — |

## 配置文件

| 文件 | 用途 |
|------|------|
| `backend/pyproject.toml` | Python 依赖和项目元数据 |
| `backend/app/config.py` | 运行时配置（数据库路径、LLM 地址） |
| `frontend/package.json` | 前端依赖和脚本 |
| `frontend/vite.config.ts` | Vite 构建配置 |
| `frontend/tsconfig.json` | TypeScript 配置 |
| `llm_proxy/config.yaml` | LiteLLM 模型路由配置 |
| `llm_proxy/pyproject.toml` | 代理层 Python 依赖 |
