import { useState, useEffect, useCallback } from "react";
import { Tabs, Button, Space, Spin, Empty, Badge, message } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import NewsCard from "../components/News/NewsCard";
import { fetchNews, fetchSources, triggerSync } from "../api/news";
import type { NewsItem, SourceInfo } from "../types";
import { SOURCE_GROUPS } from "../types";

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [activeSource, setActiveSource] = useState("");
  const [activeSubSource, setActiveSubSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Build a set of source names that are non-first children in a group
  const groupedChildNames = new Set<string>();
  for (const group of Object.values(SOURCE_GROUPS)) {
    group.children.slice(1).forEach((c) => groupedChildNames.add(c.name));
  }

  const effectiveSource = SOURCE_GROUPS[activeSource]
    ? activeSubSource || ""
    : activeSource;

  const groupChildNames = SOURCE_GROUPS[activeSource]
    ? SOURCE_GROUPS[activeSource].children.map((c) => c.name)
    : [];

  const loadSources = useCallback(async () => {
    const data = await fetchSources();
    setSources(data);
  }, []);

  const loadNews = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNews(effectiveSource, 200);
      let items = data.items;
      if (SOURCE_GROUPS[activeSource] && !activeSubSource) {
        items = items.filter((i) => groupChildNames.includes(i.source));
      }
      setNews(items);
    } finally {
      setLoading(false);
    }
  }, [effectiveSource, activeSource, activeSubSource, groupChildNames]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    loadNews();
    const timer = setInterval(loadNews, 60_000);
    return () => clearInterval(timer);
  }, [loadNews]);

  // Reset sub-tab to "全部" when main tab changes
  useEffect(() => {
    if (SOURCE_GROUPS[activeSource]) {
      setActiveSubSource("");
    }
  }, [activeSource]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await triggerSync();
      message.success(`同步完成，共抓取 ${result.total} 条新闻`);
      await loadSources();
      await loadNews();
    } catch {
      message.error("同步失败");
    } finally {
      setSyncing(false);
    }
  };

  const totalCount = sources.reduce((sum, s) => sum + s.today_count, 0);

  const items = [
    {
      key: "",
      label: <Badge count={totalCount} size="small" offset={[6, -2]}>全部</Badge>,
    },
    ...sources
      .map((s) => {
        if (groupedChildNames.has(s.name)) return null;
        const group = SOURCE_GROUPS[s.name];
        if (group) {
          const groupCount = group.children.reduce((sum, c) => {
            const found = sources.find((src) => src.name === c.name);
            return sum + (found?.today_count ?? 0);
          }, 0);
          return {
            key: s.name,
            label: <Badge count={groupCount} size="small" offset={[6, -2]}>{group.label}</Badge>,
          };
        }
        return {
          key: s.name,
          label: <Badge count={s.today_count} size="small" offset={[6, -2]}>{s.label}</Badge>,
        };
      })
      .filter(Boolean),
  ];

  const activeGroup = SOURCE_GROUPS[activeSource];
  const subItems = activeGroup
    ? [
        {
          key: "",
          label: <Badge count={activeGroup.children.reduce((sum, c) => {
            const found = sources.find((s) => s.name === c.name);
            return sum + (found?.today_count ?? 0);
          }, 0)} size="small" offset={[6, -2]}>全部</Badge>,
        },
        ...activeGroup.children.map((c) => {
          const found = sources.find((s) => s.name === c.name);
          return {
            key: c.name,
            label: <Badge count={found?.today_count ?? 0} size="small" offset={[6, -2]}>{c.label}</Badge>,
          };
        }),
      ]
    : [];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Tabs
          activeKey={activeSource}
          onChange={setActiveSource}
          items={items}
          style={{ flex: 1, marginBottom: 0 }}
          size="small"
        />
        <Button icon={<SyncOutlined spin={syncing} />} onClick={handleSync} loading={syncing}>
          同步新闻
        </Button>
      </div>

      {activeGroup && (
        <Tabs
          activeKey={activeSubSource}
          onChange={setActiveSubSource}
          items={subItems}
          size="small"
          style={{ marginBottom: 8 }}
        />
      )}

      <Spin spinning={loading}>
        {news.length === 0 ? (
          <Empty description="暂无新闻，点击同步按钮抓取" />
        ) : (
          news.map((item) => <NewsCard key={item.id} item={item} sources={sources} />)
        )}
      </Spin>
    </div>
  );
}
