<!-- last-updated: 2026-06-05 -->
# AGENTS.MD

## 目的

本文件是本仓库内 AI 协作规则的唯一真源。

`.claude/` / `.cursor/` / `.trae/` 下的规则文件仅作为兼容适配层，不能再次演变成各自独立维护的 project rule 副本。

## 读取顺序

1. AGENTS.MD
2. aiDoc/README.md
3. 按任务读取 aiDoc/ 子目录
4. 仅在当前工具确实依赖时，再读取工具目录下的适配文件

若内容冲突，以 AGENTS.MD 为准。

## 仓库概览

| 目录 | 职责 |
|------|------|
| `backend/` | FastAPI 后端 — 行情数据、新闻聚合、AI 分析、板块快照 |
| `frontend/` | React + Ant Design 前端 — 大盘展示、资讯页面、AI 对话 |
| `llm_proxy/` | LiteLLM 代理 — 统一多模型 API 转发 |
| `akshare-docs/` | AKShare 库离线文档 — 查阅金融数据接口 |
| `docs/` | 项目文档 |
| `graphify-out/` | 知识图谱输出 |

## 工程规则

### 架构

后端分层：`Router (API)` → `Service` → `Model / 外部数据源`

- `backend/app/api/` — FastAPI 路由层，负责参数提取和响应格式化
- `backend/app/services/` — 业务逻辑层，调用数据源或 LLM
- `backend/app/models/` — Pydantic 模型，定义请求/响应结构
- `backend/sources/` — 新闻数据源，继承 `BaseSource` 抽象基类
- `backend/app/database.py` — SQLite 初始化，原生 SQL（无 ORM）

前端数据流：`api/ 函数` → `pages/ 组件` → `Ant Design + ECharts 渲染`

### 前后端协作 / API 契约

- 后端运行在 `http://localhost:8001`，API 前缀 `/api/v1`
- 前端开发服务器 `http://localhost:5173`，通过 CORS 代理访问后端
- 响应直接返回 Pydantic 序列化 JSON，无统一信封包装
- 字段命名统一使用 snake_case

### 模块与目录

- `backend/app/api/market.py` — 大盘行情接口
- `backend/app/api/news.py` — 新闻聚合接口
- `backend/app/api/chat.py` — AI 对话接口
- `backend/app/api/proxy.py` — LLM 代理状态接口
- `backend/app/api/market_analysis.py` — AI 市场分析接口
- `backend/sources/` — 各新闻源实现（财联社、东方财富、新浪、同花顺等）
- `frontend/src/api/` — axios 请求封装
- `frontend/src/pages/` — 页面组件
- `frontend/src/components/` — 共享组件（Layout、Dashboard、News）

### 数据获取优先级

1. **优先使用 akshare** — `import akshare as ak`，参考 `akshare-docs/` 查找接口
2. **仅在 akshare 无对应接口时**，才使用东方财富等 HTTP API

### 示例文档

`aiDoc/examples/` 是讲解型示例层，展示每层的代码组织标准，非强制模板。

### 记忆规则

- `aiDoc/memory/long-term/` — 跨任务稳定偏好
- `aiDoc/memory/business/` — 每次业务需求记录

### 文档维护

- 高层规则写在 AGENTS.MD
- 细节和引用拆到 aiDoc/ 对应子目录
- 临时草稿不入库

### 代码读取约束

禁止读取：`node_modules/`、`.venv/`、`__pycache__/`、`backend/data/`、`graphify-out/cache/`

## AI 文档索引

- `aiDoc/README.md` — 文档索引和使用指南
- `aiDoc/relations/repo-profile.md` — 项目定位与技术栈
- `aiDoc/relations/development-workflow.md` — 开发流程与提交规范
- `aiDoc/relations/system-map.md` — 系统架构与组件关系
- `aiDoc/modules/backend-layer-rules.md` — 后端分层约束
- `aiDoc/modules/module-development.md` — 模块开发指南
- `aiDoc/frontend-backend/boundary.md` — 前后端边界与数据契约
- `aiDoc/frontend-backend/frontend-rules.md` — 前端开发规范
- `aiDoc/frontend-backend/frontend-utils.md` — 前端工具函数复用规则
- `aiDoc/examples/README.md` — 示例层说明
- `aiDoc/examples/backend/model-example.md` — Model 层示例
- `aiDoc/examples/backend/schema-example.md` — Schema 层示例
- `aiDoc/examples/backend/service-example.md` — Service 层示例
- `aiDoc/examples/backend/endpoint-example.md` — Endpoint 层示例
- `aiDoc/examples/backend/router-example.md` — Router 层示例
- `aiDoc/examples/frontend/api-example.md` — API 封装示例
- `aiDoc/examples/frontend/view-example.md` — 页面组件示例
- `aiDoc/memory/README.md` — 记忆层说明
- `aiDoc/memory/project-memory.md` — 项目记忆索引
- `aiDoc/memory/long-term/README.md` — 长期记忆
- `aiDoc/memory/business/README.md` — 业务需求记忆
- `aiDoc/memory/business/TEMPLATE.md` — 需求记录模板
