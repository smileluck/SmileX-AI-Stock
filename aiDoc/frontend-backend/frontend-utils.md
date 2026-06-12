<!-- last-updated: 2026-06-05 -->
# 前端工具函数复用规则

## 核心原则

先查现有工具和常量，不重复造轮子。

## 关键工具与常量

### HTTP 客户端

| 文件 | 用途 |
|------|------|
| `src/api/client.ts` | axios 实例，baseURL 已配置为 `http://localhost:8801/api/v1` |

所有 API 请求必须通过此 client 发起，不要在组件中直接创建 axios 实例。

### 类型定义

| 文件 | 用途 |
|------|------|
| `src/types/index.ts` | 所有 TypeScript interface 集中定义 |

新增类型必须添加到此文件，与后端 Pydantic Model 保持一致。

### 常量映射

| 文件 | 包含 |
|------|------|
| `src/types/index.ts` | `SOURCE_GROUPS`（数据源分组）、`SOURCE_COLOR_MAP`（数据源颜色映射） |

使用场景：
- 新闻页面数据源筛选 → 使用 `SOURCE_GROUPS`
- 数据源标签颜色 → 使用 `SOURCE_COLOR_MAP`

### API 封装

| 文件 | 覆盖模块 |
|------|----------|
| `src/api/market.ts` | 大盘行情 |
| `src/api/marketAnalysis.ts` | AI 分析 |
| `src/api/news.ts` | 新闻 |
| `src/api/sector.ts` | 板块 |
| `src/api/chat.ts` | AI 对话 |
| `src/api/aiConfig.ts` | LLM 代理配置 |

新增 API 必须在对应文件中添加函数，不要在页面组件中直接调用 `client.get/post`。

## 强制使用场景清单

| 场景 | 必须使用 |
|------|----------|
| 发起 HTTP 请求 | `src/api/client.ts` 的 axios 实例 |
| 定义 API 响应类型 | `src/types/index.ts` 中的 interface |
| 显示数据源标签 | `SOURCE_COLOR_MAP` |
| 数据源分组显示 | `SOURCE_GROUPS` |
| 日期格式化 | `dayjs`（已安装依赖） |
