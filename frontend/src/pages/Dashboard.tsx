import { useState, useCallback } from "react";
import { Button, Spin, Alert, Typography } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import IndexSection from "../components/Dashboard/IndexSection";
import { fetchMarketOverview } from "../api/market";
import { usePolling } from "../hooks/usePolling";
import type { MarketOverviewResponse } from "../types";

export default function Dashboard() {
  const [data, setData] = useState<MarketOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMarketOverview();
      setData(res);
    } catch {
      setError("获取市场数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(loadData, 30_000);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>大盘概览</Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {data?.fetch_time && (
            <span style={{ fontSize: 12, color: "#999" }}>更新于 {data.fetch_time}</span>
          )}
          <Button icon={<SyncOutlined spin={loading} />} onClick={loadData} size="small">
            刷新
          </Button>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Spin spinning={loading && !data}>
        {data && (
          <>
            <IndexSection title="沪深重要指数" indices={data.cn_main} />
            <IndexSection title="全球指数" indices={data.international} />
          </>
        )}
      </Spin>
    </div>
  );
}
