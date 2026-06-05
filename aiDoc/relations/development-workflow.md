<!-- last-updated: 2026-06-05 -->
# 开发流程与提交规范

## 推荐开发顺序

1. 后端：定义 Model → 实现 Service → 创建 API Endpoint → 注册 Router
2. 前端：定义类型 → 封装 API 函数 → 创建页面组件 → 添加路由
3. 联调：前后端接口对齐，验证数据格式

## 前后端协作

- 后端先实现接口，确保返回格式与 Pydantic Model 一致
- 前端并行开发，使用 TypeScript 类型与后端 Model 对齐
- 联调时通过浏览器 DevTools 检查实际响应

## 分支策略

- `main` — 主分支，稳定代码
- `feature/*` — 功能分支
- `hotfix/*` — 紧急修复

## 提交规范

格式：`type(scope): description`

| type | 用途 |
|------|------|
| feat | 新功能 |
| fix | 修复 bug |
| refactor | 重构 |
| docs | 文档变更 |
| chore | 构建/配置变更 |

示例：`feat(market): add sector capital flow API`

## 环境与依赖

### 后端启动

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8001
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### LLM 代理启动

```bash
cd llm_proxy
uv sync
uv run litellm --config config.yaml --port 4000
```

## 环境变量

后端通过 `.env` 文件配置（`backend/` 目录下）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LITELLM_PROXY_URL` | LiteLLM 代理地址 | `http://localhost:4000` |
| `LITELLM_MASTER_KEY` | 代理认证密钥 | 空 |
