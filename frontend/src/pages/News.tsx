import { useState, useEffect, useCallback } from "react";
import { Tabs, Button, Space, Spin, Empty, Badge, message } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import NewsCard from "../components/News/NewsCard";
import { fetchNews, fetchSources, triggerSync } from "../api/news";
import type { NewsItem, SourceInfo } from "../types";

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [activeSource, setActiveSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const loadSources = useCallback(async () => {
    const data = await fetchSources();
    setSources(data);
  }, []);

  const loadNews = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNews(activeSource, 200);
      setNews(data.items);
    } finally {
      setLoading(false);
    }
  }, [activeSource]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    loadNews();
    const timer = setInterval(loadNews, 60_000);
    return () => clearInterval(timer);
  }, [loadNews]);

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
    ...sources.map((s) => ({
      key: s.name,
      label: <Badge count={s.today_count} size="small" offset={[6, -2]}>{s.label}</Badge>,
    })),
  ];

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
