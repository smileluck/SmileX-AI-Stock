<!-- last-updated: 2026-06-05 -->
# 前后端边界与数据契约

## 责任边界

| 职责 | 后端 | 前端 |
|------|------|------|
| 数据获取 | akshare、东方财富 API | — |
| 业务逻辑 | 计算、LLM 调用、定时任务 | — |
| 数据存储 | SQLite 持久化 | — |
| API 提供 | FastAPI Endpoint | — |
| 数据展示 | — | Ant Design 表格/卡片 |
| 图表渲染 | — | ECharts 折线/K 线图 |
| 路由与导航 | — | React Router |
| HTTP 请求 | — | Axios（通过 `src/api/client.ts`） |

## 统一响应结构

本项目无统一信封包装。每个接口直接返回业务数据，格式由 Pydantic Model 定义。

### 典型响应结构

```json
{
  "cn_main": [...],
  "international": [...],
  "fetch_time": "2026-06-05 15:30:00"
}
```

```json
{
  "items": [...],
  "total": 100
}
```

### 操作类响应

```json
{
  "success": true,
  "message": "ok",
  "trade_date": "2026-06-05"
}
```

## 字段命名规范

- 后端 Python：snake_case（如 `change_pct`、`fetch_time`）
- 前端 TypeScript：snake_case（与后端保持一致）
- JSON 序列化：snake_case

前后端字段名完全一致，不做 camelCase 转换。

## 时间字段

- 格式：`YYYY-MM-DD HH:MM:SS`（如 `2026-06-05 15:30:00`）
- 日期字段：`YYYY-MM-DD`（如 `trade_date`）
- 时区：使用服务器本地时间，不做时区转换

## 可空字段处理

- 后端：`float | None = None`
- 前端：`number | null`
- JSON 序列化：`null`

## 变更规则

1. 后端新增字段必须在 Pydantic Model 中声明默认值
2. 前端 TypeScript 类型必须同步更新
3. 破坏性变更（删字段、改类型）需要前后端协调

## 完成前检查清单

- [ ] 后端 Pydantic Model 字段与前端 TypeScript interface 一致
- [ ] 响应字段使用 snake_case
- [ ] 可空字段使用 `| None` / `| null`
- [ ] 时间字段格式统一为 `YYYY-MM-DD HH:MM:SS`
