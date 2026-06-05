<!-- last-updated: 2026-06-05 -->
# API 封装示例

## 用途

展示前端 API 函数的封装方式：axios 请求、类型标注、错误处理。

## 核心原则

- 统一使用 `src/api/client.ts` 的 axios 实例
- 函数返回类型标注为对应 Response 类型
- 函数名使用 `fetch` 前缀

## 示例

```typescript
// src/api/market.ts
import client from "./client";
import type { MarketOverviewResponse, MarketHistoryResponse } from "../types";

export async function fetchMarketOverview(): Promise<MarketOverviewResponse> {
  const { data } = await client.get("/market/overview");
  return data;
}

export async function fetchMarketHistory(days = 30): Promise<MarketHistoryResponse> {
  const { data } = await client.get("/market/history", { params: { days } });
  return data;
}
```

## 关键点

- `client.get` 自动添加 `/api/v1` 前缀
- 使用解构 `{ data }` 直接提取响应体
- Query 参数通过 `params` 对象传递
- 类型 import 使用 `import type` 语法

## 真实参考文件

- `src/api/market.ts` — 大盘行情 API
- `src/api/news.ts` — 新闻 API
- `src/api/chat.ts` — AI 对话 API
