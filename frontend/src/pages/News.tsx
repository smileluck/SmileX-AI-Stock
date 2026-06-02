import { useState, useEffect, useCallback } from "react";
import { Select, Button, Space, Spin, Empty, message } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import NewsCard from "../components/News/NewsCard";
import { fetchNews, fetchSources, triggerSync } from "../api/news";
import type { NewsItem, SourceInfo } from "../types";

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const loadSources = useCallback(async () => {
    const data = await fetchSources();
    setSources(data);
  }, []);

  const loadNews = useCallback(async () => {
    setLoading(true);
    try {
      const source = selectedSources.length === 1 ? selectedSources[0] : "";
      const data = await fetchNews(source, 200);
      setNews(
        selectedSources.length > 1
          ? data.items.filter((i) => selectedSources.includes(i.source))
          : data.items,
      );
    } finally {
      setLoading(false);
    }
  }, [selectedSources]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    loadNews();
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

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Select
          mode="multiple"
          placeholder="按来源筛选"
          value={selectedSources}
          onChange={setSelectedSources}
          style={{ minWidth: 300 }}
          options={sources.map((s) => ({ label: `${s.label} (${s.count})`, value: s.name }))}
          allowClear
        />
        <Button icon={<SyncOutlined spin={syncing} />} onClick={handleSync} loading={syncing}>
          同步新闻
        </Button>
      </Space>

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
