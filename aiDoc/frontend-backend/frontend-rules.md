<!-- last-updated: 2026-06-05 -->
# 前端开发规范

## 基础规则

- HTTP 请求：统一通过 `src/api/client.ts` 创建的 axios 实例
- 状态管理：组件内 `useState`，无全局状态库
- 路由：React Router DOM v7，在 `src/App.tsx` 中声明

## 命名规范

| 对象 | 规范 | 示例 |
|------|------|------|
| 文件名 | PascalCase | `Dashboard.tsx`、`AppLayout.tsx` |
| API 文件 | camelCase | `market.ts`、`aiConfig.ts` |
| 组件名 | PascalCase | `IndexCard`、`NewsCard` |
| API 函数 | camelCase + fetch 前缀 | `fetchMarketOverview` |
| 类型接口 | PascalCase | `MarketOverviewResponse` |
| 变量 | camelCase | `fetchTime`、`changePct` |

## TypeScript / 类型要求

- 所有 API 响应必须定义对应的 TypeScript interface
- 类型定义集中在 `src/types/index.ts`
- 与后端 Pydantic Model 字段名保持完全一致（snake_case）
- 可空字段使用 `| null`

## 组件规范

- 共享组件放 `src/components/`，按功能分子目录（Layout/、Dashboard/、News/）
- 页面组件放 `src/pages/`
- Props 使用 TypeScript interface 定义
- 使用函数组件 + Hooks

## 页面规范

新增页面必须完成：
1. 在 `src/pages/` 创建组件文件
2. 在 `src/App.tsx` 添加路由
3. 在 `src/components/Layout/Sidebar.tsx` 添加菜单项
4. 如需 API，在 `src/api/` 创建封装文件
5. 在 `src/types/index.ts` 添加类型定义

## 样式规范

- 使用 Ant Design 组件库的内置样式
- 自定义样式使用 inline style 或 CSS modules
- 不引入额外的 CSS 框架

## 图表规范

- 使用 ECharts 通过 `echarts-for-react` 包装
- 图表配置项使用 ECharts 原生 option 格式

## 常用脚本命令

| 命令 | 用途 |
|------|------|
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 构建生产版本 |
| `npm run lint` | ESLint 检查 |
| `npm run preview` | 预览构建结果 |

## 代码注释要求

- 不写显而易见的注释
- 复杂逻辑添加简短中文注释说明意图
