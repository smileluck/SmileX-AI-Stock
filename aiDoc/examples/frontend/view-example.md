<!-- last-updated: 2026-06-05 -->
# 页面组件示例

## 用途

展示前端页面组件的标准结构：数据获取、状态管理、Ant Design 组件使用。

## 核心原则

- 函数组件 + useState/useEffect
- 数据获取在 useEffect 中调用 API 函数
- 使用 Ant Design 组件（Table、Card、Tag 等）
- 类型从 `../types` 导入

## 示例

```tsx
// src/pages/News.tsx
import { useState, useEffect } from "react";
import { Table, Tag } from "antd";
import type { NewsItem } from "../types";
import { SOURCE_COLOR_MAP } from "../types";
import { fetchNews } from "../api/news";

export default function NewsPage() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchNews().then((res) => {
      setItems(res.items);
      setLoading(false);
    });
  }, []);

  const columns = [
    {
      title: "来源",
      dataIndex: "source",
      render: (source: string) => (
        <Tag color={SOURCE_COLOR_MAP[source] || "default"}>{source}</Tag>
      ),
    },
    { title: "标题", dataIndex: "title" },
    { title: "时间", dataIndex: "publish_time" },
  ];

  return (
    <Table
      columns={columns}
      dataSource={items}
      loading={loading}
      rowKey="id"
    />
  );
}
```

## 关键点

- `useState<NewsItem[]>([])` — 泛型指定状态类型
- `useEffect` 依赖数组为空 `[]`，只在挂载时获取数据
- `SOURCE_COLOR_MAP` 提供统一的标签颜色
- `rowKey="id"` 确保列表渲染性能

## 真实参考文件

- `src/pages/Dashboard.tsx` — 大盘概览页面
- `src/pages/News.tsx` — 新闻列表页面
- `src/pages/AIChat.tsx` — AI 对话页面
