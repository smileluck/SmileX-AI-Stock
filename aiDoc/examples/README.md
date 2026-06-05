<!-- last-updated: 2026-06-05 -->
# 示例层

aiDoc/examples/ 是讲解型示例层，告诉 AI 每一层应该按什么标准组织和书写。

## 用途

- 示例不是要求逐字复制，而是展示项目标准的代码组织方式
- 当 AI 需要新增某一层文件时，应先阅读对应示例

## 后端开发阅读顺序

1. [model-example.md](backend/model-example.md) — Pydantic Model 示例
2. [schema-example.md](backend/schema-example.md) — 请求/响应 Schema 示例
3. [service-example.md](backend/service-example.md) — Service 层示例
4. [endpoint-example.md](backend/endpoint-example.md) — API 端点示例
5. [router-example.md](backend/router-example.md) — 路由注册示例

## 前端开发阅读顺序

1. [api-example.md](frontend/api-example.md) — API 封装示例
2. [view-example.md](frontend/view-example.md) — 页面组件示例

## 原则

- 仓库真实代码与示例不一致时，以真实代码为准，并更新示例
