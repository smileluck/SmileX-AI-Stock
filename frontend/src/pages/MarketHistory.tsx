import { useState, useEffect, useCallback, useMemo } from "react";
import { Button, Spin, Alert, Typography, Segmented, Select, Table } from "antd";
import { SyncOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { fetchMarketHistory } from "../api/market";
import type { MarketHistoryResponse, IndexDailyItem } from "../types";

const DAY_OPTIONS = [
  { label: "7天", value: 7 },
  { label: "15天", value: 15 },
  { label: "30天", value: 30 },
  { label: "90天", value: 90 },
  { label: "180天", value: 180 },
];

const tableColumns = [
  { title: "日期", dataIndex: "date", key: "date", sorter: (a: IndexDailyItem, b: IndexDailyItem) => a.date.localeCompare(b.date), defaultSortOrder: "descend" as const },
  { title: "开盘", dataIndex: "open", key: "open", render: (v: number) => v.toFixed(2) },
  { title: "收盘", dataIndex: "close", key: "close", render: (v: number) => v.toFixed(2) },
  { title: "最高", dataIndex: "high", key: "high", render: (v: number) => v.toFixed(2) },
  { title: "最低", dataIndex: "low", key: "low", render: (v: number) => v.toFixed(2) },
  {
    title: "成交量", dataIndex: "volume", key: "volume",
    render: (v: number) => {
      if (v >= 1_000_000_00) return (v / 1_000_000_00).toFixed(2) + "亿";
      if (v >= 1_0000) return (v / 1_0000).toFixed(2) + "万";
      return v.toLocaleString();
    },
  },
];

export default function MarketHistory() {
  const [data, setData] = useState<MarketHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [selectedIndex, setSelectedIndex] = useState("sh000001");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMarketHistory(days);
      setData(res);
      const codes = res.indices.map((i) => i.code);
      if (!codes.includes(selectedIndex)) {
        setSelectedIndex(codes[0] ?? "sh000001");
      }
    } catch {
      setError("获取历史数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, [days, selectedIndex]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const currentIndex = useMemo(
    () => data?.indices.find((i) => i.code === selectedIndex),
    [data, selectedIndex],
  );

  const chartOption = useMemo(() => {
    if (!currentIndex || currentIndex.records.length === 0) return {};
    const records = currentIndex.records;
    return {
      tooltip: {
        trigger: "axis" as const,
        formatter: (params: { name: string; value: number }[]) => {
          const p = params[0];
          const r = records.find((x) => x.date === p.name);
          if (!r) return "";
          return `${r.date}<br/>开盘: ${r.open.toFixed(2)}<br/>收盘: ${r.close.toFixed(2)}<br/>最高: ${r.high.toFixed(2)}<br/>最低: ${r.low.toFixed(2)}`;
        },
      },
      grid: { left: 60, right: 20, top: 20, bottom: 60 },
      xAxis: { type: "category" as const, data: records.map((r) => r.date) },
      yAxis: { type: "value" as const, scale: true },
      dataZoom: [{ type: "inside" as const }, { type: "slider" as const }],
      series: [
        {
          type: "line" as const,
          data: records.map((r) => r.close),
          smooth: true,
          areaStyle: { opacity: 0.1 },
          lineStyle: { width: 2 },
        },
      ],
    };
  }, [currentIndex]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>历史大盘</Typography.Title>
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

      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <Segmented
          options={DAY_OPTIONS}
          value={days}
          onChange={(v) => setDays(v as number)}
        />
        <Select
          value={selectedIndex}
          onChange={setSelectedIndex}
          style={{ width: 160 }}
          options={data?.indices.map((i) => ({ value: i.code, label: i.name })) ?? []}
        />
      </div>

      <Spin spinning={loading && !data}>
        {currentIndex && (
          <>
            <ReactECharts
              option={chartOption}
              style={{ height: 400, marginBottom: 24 }}
              notMerge
              lazyUpdate
            />
            <Table
              dataSource={currentIndex.records}
              columns={tableColumns}
              rowKey="date"
              size="small"
              pagination={{ pageSize: 15, showSizeChanger: false }}
            />
          </>
        )}
      </Spin>
    </div>
  );
}
