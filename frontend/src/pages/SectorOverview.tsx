import { useState, useCallback, useMemo } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Segmented,
  Tabs,
  Table,
} from "antd";
import { SyncOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { fetchSectorOverview, fetchSectorCapitalFlow } from "../api/sector";
import type {
  SectorItem,
  SectorCapitalFlowItem,
  SectorOverviewResponse,
  SectorCapitalFlowResponse,
} from "../types";
import { usePolling } from "../hooks/usePolling";
import { POSITIVE_COLOR, NEGATIVE_COLOR, fmtPct, fmtAmount, pctColor } from "../utils/format";

// ── Change trend columns ──
const trendColumns = [
  {
    title: "排名",
    width: 60,
    render: (_: unknown, __: unknown, idx: number) => idx + 1,
  },
  { title: "板块名称", dataIndex: "name", key: "name", width: 140 },
  {
    title: "最新价",
    dataIndex: "price",
    key: "price",
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "涨跌幅",
    dataIndex: "change_pct",
    key: "change_pct",
    sorter: (a: SectorItem, b: SectorItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>
    ),
  },
  {
    title: "涨跌额",
    dataIndex: "change",
    key: "change",
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>
        {v != null ? `${v > 0 ? "+" : ""}${v.toFixed(2)}` : "--"}
      </span>
    ),
  },
  {
    title: "成交额",
    dataIndex: "amount",
    key: "amount",
    render: (v: number | null) => fmtAmount(v),
  },
  {
    title: "涨/跌/平",
    key: "counts",
    render: (_: unknown, r: SectorItem) =>
      r.up_count != null ? (
        <span>
          <span style={{ color: POSITIVE_COLOR }}>{Math.round(r.up_count)}</span>
          {" / "}
          <span style={{ color: NEGATIVE_COLOR }}>{Math.round(r.down_count)}</span>
          {" / "}
          {Math.round(r.flat_count ?? 0)}
        </span>
      ) : (
        "--"
      ),
  },
  {
    title: "领涨股",
    key: "leading_stock",
    render: (_: unknown, r: SectorItem) =>
      r.leading_stock ? (
        <>
          {r.leading_stock}{" "}
          <span style={{ color: pctColor(r.leading_stock_change_pct), fontSize: 12 }}>
            {fmtPct(r.leading_stock_change_pct)}
          </span>
        </>
      ) : (
        "--"
      ),
  },
];

// ── Capital flow columns ──
const flowColumns = [
  {
    title: "排名",
    width: 60,
    render: (_: unknown, __: unknown, idx: number) => idx + 1,
  },
  { title: "板块名称", dataIndex: "name", key: "name", width: 140 },
  {
    title: "涨跌幅",
    dataIndex: "change_pct",
    key: "change_pct",
    sorter: (a: SectorCapitalFlowItem, b: SectorCapitalFlowItem) =>
      (a.change_pct ?? 0) - (b.change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>
    ),
  },
  {
    title: "主力净流入",
    dataIndex: "main_net_inflow",
    key: "main_net_inflow",
    sorter: (a: SectorCapitalFlowItem, b: SectorCapitalFlowItem) =>
      (a.main_net_inflow ?? 0) - (b.main_net_inflow ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>
    ),
  },
  {
    title: "主力净流入占比",
    dataIndex: "main_net_inflow_pct",
    key: "main_net_inflow_pct",
    render: (v: number | null) => (v != null ? `${v.toFixed(2)}%` : "--"),
  },
  {
    title: "超大单净流入",
    dataIndex: "super_large_net",
    key: "super_large_net",
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>
    ),
  },
  {
    title: "大单净流入",
    dataIndex: "large_net",
    key: "large_net",
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>
    ),
  },
  {
    title: "中单净流入",
    dataIndex: "medium_net",
    key: "medium_net",
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>
    ),
  },
  {
    title: "小单净流入",
    dataIndex: "small_net",
    key: "small_net",
    render: (v: number | null) => (
      <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>
    ),
  },
];

// ── Chart helpers ──
function trendChartOption(items: SectorItem[]) {
  const top5 = items.slice(0, 5);
  const bottom5 = [...items].reverse().slice(0, 5);
  const combined = [...top5, ...bottom5.reverse()];

  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { name: string; value: number }[]) => {
        const p = params[0];
        return `${p.name}<br/>涨跌幅: ${fmtPct(p.value)}`;
      },
    },
    grid: { left: 100, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => `${v}%` } },
    yAxis: {
      type: "category" as const,
      data: combined.map((i) => i.name),
      inverse: true,
    },
    series: [
      {
        type: "bar" as const,
        data: combined.map((i) => ({
          value: i.change_pct ?? 0,
          itemStyle: { color: (i.change_pct ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR },
        })),
      },
    ],
  };
}

function flowChartOption(items: SectorCapitalFlowItem[]) {
  const top10 = items.slice(0, 10);
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { name: string; value: number }[]) => {
        const p = params[0];
        return `${p.name}<br/>主力净流入: ${fmtAmount(p.value)}`;
      },
    },
    grid: { left: 100, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: "value" as const,
      axisLabel: { formatter: (v: number) => fmtAmount(v) },
    },
    yAxis: {
      type: "category" as const,
      data: top10.map((i) => i.name),
      inverse: true,
    },
    series: [
      {
        type: "bar" as const,
        data: top10.map((i) => ({
          value: i.main_net_inflow ?? 0,
          itemStyle: { color: (i.main_net_inflow ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR },
        })),
      },
    ],
  };
}

// ── Main page ──
type ViewMode = "trend" | "flow";

export default function SectorOverview() {
  const [overview, setOverview] = useState<SectorOverviewResponse | null>(null);
  const [flow, setFlow] = useState<SectorCapitalFlowResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("trend");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, fl] = await Promise.all([
        fetchSectorOverview(),
        fetchSectorCapitalFlow(),
      ]);
      setOverview(ov);
      setFlow(fl);
    } catch {
      setError("获取板块数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(loadData, 30_000);

  const fetchTime = viewMode === "trend" ? overview?.fetch_time : flow?.fetch_time;

  const renderTrendPanel = (items: SectorItem[]) => {
    const sorted = [...items].sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0));
    return (
      <>
        <ReactECharts
          option={trendChartOption(sorted)}
          style={{ height: 320, marginBottom: 16 }}
          notMerge
          lazyUpdate
        />
        <Table
          dataSource={sorted}
          columns={trendColumns}
          rowKey="code"
          size="small"
          pagination={{ pageSize: 15, showSizeChanger: false }}
        />
      </>
    );
  };

  const renderFlowPanel = (items: SectorCapitalFlowItem[]) => {
    const sorted = [...items].sort((a, b) => (b.main_net_inflow ?? 0) - (a.main_net_inflow ?? 0));
    return (
      <>
        <ReactECharts
          option={flowChartOption(sorted)}
          style={{ height: 320, marginBottom: 16 }}
          notMerge
          lazyUpdate
        />
        <Table
          dataSource={sorted}
          columns={flowColumns}
          rowKey="code"
          size="small"
          pagination={{ pageSize: 15, showSizeChanger: false }}
          scroll={{ x: 900 }}
        />
      </>
    );
  };

  const tabItems = useMemo(() => {
    const industryData = viewMode === "trend" ? overview?.industry : flow?.industry;
    const conceptData = viewMode === "trend" ? overview?.concept : flow?.concept;
    return [
      {
        key: "industry",
        label: "行业板块",
        children: industryData
          ? viewMode === "trend"
            ? renderTrendPanel(industryData as SectorItem[])
            : renderFlowPanel(industryData as SectorCapitalFlowItem[])
          : null,
      },
      {
        key: "concept",
        label: "概念板块",
        children: conceptData
          ? viewMode === "trend"
            ? renderTrendPanel(conceptData as SectorItem[])
            : renderFlowPanel(conceptData as SectorCapitalFlowItem[])
          : null,
      },
    ];
  }, [viewMode, overview, flow]);

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          今日板块
        </Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {fetchTime && (
            <span style={{ fontSize: 12, color: "#999" }}>更新于 {fetchTime}</span>
          )}
          <Button
            icon={<SyncOutlined spin={loading} />}
            onClick={loadData}
            size="small"
          >
            刷新
          </Button>
        </div>
      </div>

      {error && (
        <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}

      <div style={{ marginBottom: 16 }}>
        <Segmented
          options={[
            { label: "涨跌幅趋势", value: "trend" },
            { label: "资金流向", value: "flow" },
          ]}
          value={viewMode}
          onChange={(v) => setViewMode(v as ViewMode)}
        />
      </div>

      <Spin spinning={loading && !overview}>
        <Tabs items={tabItems} />
      </Spin>
    </div>
  );
}
