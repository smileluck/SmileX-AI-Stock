import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Tabs, Button, Spin, Empty, Badge, message } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import NewsCard from "../components/News/NewsCard";
import { fetchNews, fetchSources, triggerSync } from "../api/news";
import type { NewsItem, SourceInfo } from "../types";
import { SOURCE_GROUPS } from "../types";

// Build a set of source names that are non-first children in a group
const GROUPED_CHILD_NAMES = new Set<string>();
for (const group of Object.values(SOURCE_GROUPS)) {
  group.children.slice(1).forEach((c) => GROUPED_CHILD_NAMES.add(c.name));
}

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [activeSource, setActiveSource] = useState("");
  const [activeSubSource, setActiveSubSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const activeGroup = SOURCE_GROUPS[activeSource];
  const groupChildNames = useMemo(
    () => activeGroup?.children.map((c) => c.name) ?? [],
    [activeGroup]
  );

  const effectiveSource = activeGroup
    ? activeSubSource || ""
    : activeSource;

  const loadSources = useCallback(async () => {
    const data = await fetchSources();
    setSources(data);
  }, []);

  const fetchRef = useRef({ effectiveSource, activeGroup, activeSubSource, groupChildNames });
  fetchRef.current = { effectiveSource, activeGroup, activeSubSource, groupChildNames };

  const loadNews = useCallback(async () => {
    setLoading(true);
    try {
      const { effectiveSource: es, activeGroup: ag, activeSubSource: asub, groupChildNames: gcn } = fetchRef.current;
      const data = await fetchNews(es, 200);
      let items = data.items;
      if (ag && !asub) {
        items = items.filter((i) => gcn.includes(i.source));
      }
      setNews(items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    loadNews();
    const timer = setInterval(loadNews, 60_000);
    return () => clearInterval(timer);
  }, [loadNews, effectiveSource, activeSubSource]);

  const handleTabChange = useCallback((key: string) => {
    setActiveSource(key);
    if (SOURCE_GROUPS[key]) {
      setActiveSubSource("");
    }
  }, []);

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
        if (GROUPED_CHILD_NAMES.has(s.name)) return null;
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
          onChange={handleTabChange}
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
