import { useState, useEffect, useCallback } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Segmented,
  Tabs,
  Table,
  DatePicker,
  Select,
  message,
  Empty,
} from "antd";
import { CameraOutlined, SyncOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";
import {
  fetchSectorHistoryByDate,
  fetchSectorHistoryRange,
  fetchSectorTrend,
  fetchSectorAvailableDates,
  triggerSectorSnapshot,
} from "../api/sector";
import type {
  SectorHistoryItem,
  SectorHistoryDateResponse,
  SectorAggregatedItem,
  SectorHistoryRangeResponse,
  SectorTrendResponse,
} from "../types";

const { RangePicker } = DatePicker;

const POSITIVE_COLOR = "#cf1322";
const NEGATIVE_COLOR = "#3f8600";

function pctColor(v: number | null): string | undefined {
  if (v == null) return undefined;
  return v > 0 ? POSITIVE_COLOR : v < 0 ? NEGATIVE_COLOR : undefined;
}

function fmtPct(v: number | null): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtAmount(v: number | null): string {
  if (v == null) return "--";
  if (Math.abs(v) >= 1_0000_0000) return (v / 1_0000_0000).toFixed(2) + "亿";
  if (Math.abs(v) >= 1_0000) return (v / 1_0000).toFixed(2) + "万";
  return v.toLocaleString();
}

// ── Single-day columns ──
const singleDayColumns = [
  { title: "排名", width: 60, render: (_: unknown, __: unknown, idx: number) => idx + 1 },
  { title: "板块名称", dataIndex: "name", key: "name", width: 140 },
  {
    title: "涨跌幅",
    dataIndex: "change_pct",
    key: "change_pct",
    sorter: (a: SectorHistoryItem, b: SectorHistoryItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
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
    render: (_: unknown, r: SectorHistoryItem) =>
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
    render: (_: unknown, r: SectorHistoryItem) =>
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
  {
    title: "主力净流入",
    dataIndex: "main_net_inflow",
    key: "main_net_inflow",
    sorter: (a: SectorHistoryItem, b: SectorHistoryItem) =>
      (a.main_net_inflow ?? 0) - (b.main_net_inflow ?? 0),
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>,
  },
];

// ── Range aggregated columns ──
const rangeColumns = [
  { title: "排名", width: 60, render: (_: unknown, __: unknown, idx: number) => idx + 1 },
  { title: "板块名称", dataIndex: "name", key: "name", width: 140 },
  {
    title: "平均涨跌幅",
    dataIndex: "avg_change_pct",
    key: "avg_change_pct",
    sorter: (a: SectorAggregatedItem, b: SectorAggregatedItem) =>
      (a.avg_change_pct ?? 0) - (b.avg_change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
  },
  {
    title: "累计主力净流入",
    dataIndex: "total_main_net_inflow",
    key: "total_main_net_inflow",
    sorter: (a: SectorAggregatedItem, b: SectorAggregatedItem) =>
      (a.total_main_net_inflow ?? 0) - (b.total_main_net_inflow ?? 0),
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtAmount(v)}</span>,
  },
  {
    title: "最佳日涨幅",
    dataIndex: "best_change_pct",
    key: "best_change_pct",
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
  },
  {
    title: "最差日跌幅",
    dataIndex: "worst_change_pct",
    key: "worst_change_pct",
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
  },
  {
    title: "交易日天数",
    dataIndex: "trading_days",
    key: "trading_days",
    width: 100,
  },
];

// ── Chart builders ──
function buildTrendBarChart(items: SectorHistoryItem[]) {
  const top5 = items.slice(0, 5);
  const bottom5 = [...items].reverse().slice(0, 5);
  const combined = [...top5, ...bottom5.reverse()];
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { name: string; value: number }[]) =>
        `${params[0].name}<br/>涨跌幅: ${fmtPct(params[0].value)}`,
    },
    grid: { left: 100, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => `${v}%` } },
    yAxis: { type: "category" as const, data: combined.map((i) => i.name), inverse: true },
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

function buildFlowBarChart(items: SectorHistoryItem[]) {
  const top10 = items.slice(0, 10);
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { name: string; value: number }[]) =>
        `${params[0].name}<br/>主力净流入: ${fmtAmount(params[0].value)}`,
    },
    grid: { left: 100, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => fmtAmount(v) } },
    yAxis: { type: "category" as const, data: top10.map((i) => i.name), inverse: true },
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

function buildRangeBarChart(sectors: SectorAggregatedItem[]) {
  const top10 = sectors.slice(0, 10);
  const bottom10 = [...sectors].reverse().slice(0, 10);
  const combined = [...top10, ...bottom10.reverse()];
  return {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: { name: string; value: number }[]) =>
        `${params[0].name}<br/>平均涨跌幅: ${fmtPct(params[0].value)}`,
    },
    grid: { left: 120, right: 20, top: 20, bottom: 40 },
    xAxis: { type: "value" as const, axisLabel: { formatter: (v: number) => `${v}%` } },
    yAxis: { type: "category" as const, data: combined.map((i) => i.name), inverse: true },
    series: [
      {
        type: "bar" as const,
        data: combined.map((i) => ({
          value: i.avg_change_pct ?? 0,
          itemStyle: { color: (i.avg_change_pct ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR },
        })),
      },
    ],
  };
}

function buildTrendLineChart(trend: SectorTrendResponse) {
  const dates = trend.data.map((d) => d.date);
  return {
    tooltip: { trigger: "axis" as const },
    legend: { data: ["涨跌幅", "主力净流入"], top: 0 },
    grid: { left: 60, right: 80, top: 40, bottom: 60 },
    xAxis: { type: "category" as const, data: dates, boundaryGap: false },
    yAxis: [
      { type: "value" as const, name: "涨跌幅(%)", axisLabel: { formatter: (v: number) => `${v}%` } },
      {
        type: "value" as const,
        name: "主力净流入",
        axisLabel: { formatter: (v: number) => fmtAmount(v) },
      },
    ],
    dataZoom: [
      { type: "inside" as const, start: 0, end: 100 },
      { type: "slider" as const, start: 0, end: 100, height: 20, bottom: 8 },
    ],
    series: [
      {
        name: "涨跌幅",
        type: "line" as const,
        data: trend.data.map((d) => d.change_pct),
        yAxisIndex: 0,
        itemStyle: { color: "#1890ff" },
        areaStyle: { opacity: 0.1 },
      },
      {
        name: "主力净流入",
        type: "bar" as const,
        data: trend.data.map((d) => d.main_net_inflow),
        yAxisIndex: 1,
        itemStyle: {
          color: (params: { value: number | null }) =>
            (params.value ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR,
        },
      },
    ],
  };
}

// ── Main page ──
type QueryMode = "single" | "range";
type SectorType = "industry" | "concept";

export default function SectorHistory() {
  const [queryMode, setQueryMode] = useState<QueryMode>("single");
  const [sectorType, setSectorType] = useState<SectorType>("industry");

  // available dates
  const [availableDates, setAvailableDates] = useState<string[]>([]);

  // single-day state
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [singleData, setSingleData] = useState<SectorHistoryDateResponse | null>(null);
  const [singleTab, setSingleTab] = useState<string>("trend");

  // range state
  const [dateRange, setDateRange] = useState<[string, string]>([
    dayjs().subtract(7, "day").format("YYYY-MM-DD"),
    dayjs().format("YYYY-MM-DD"),
  ]);
  const [rangeData, setRangeData] = useState<SectorHistoryRangeResponse | null>(null);
  const [trendCode, setTrendCode] = useState<string>("");
  const [trendData, setTrendData] = useState<SectorTrendResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // load available dates
  const loadDates = useCallback(async () => {
    try {
      const res = await fetchSectorAvailableDates(sectorType);
      setAvailableDates(res.dates);
    } catch {
      // silent - dates will be empty
    }
  }, [sectorType]);

  useEffect(() => {
    loadDates();
  }, [loadDates]);

  // load single-day data
  const loadSingleData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSectorHistoryByDate(selectedDate, sectorType);
      setSingleData(res);
    } catch {
      setError("查询历史数据失败");
      setSingleData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedDate, sectorType]);

  // load range data
  const loadRangeData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSectorHistoryRange(dateRange[0], dateRange[1], sectorType);
      setRangeData(res);
      // auto-select first sector for trend
      if (res.sectors.length > 0 && !trendCode) {
        setTrendCode(res.sectors[0].code);
      }
    } catch {
      setError("查询区间统计失败");
      setRangeData(null);
    } finally {
      setLoading(false);
    }
  }, [dateRange, sectorType, trendCode]);

  // load trend data
  const loadTrendData = useCallback(async () => {
    if (!trendCode || !dateRange[0] || !dateRange[1]) return;
    try {
      const res = await fetchSectorTrend(trendCode, sectorType, dateRange[0], dateRange[1]);
      setTrendData(res);
    } catch {
      setTrendData(null);
    }
  }, [trendCode, sectorType, dateRange]);

  // initial load when mode/type changes
  useEffect(() => {
    if (queryMode === "single" && selectedDate) {
      loadSingleData();
    } else if (queryMode === "range" && dateRange[0] && dateRange[1]) {
      loadRangeData();
    }
  }, [queryMode, sectorType]);

  // load trend when code or range changes
  useEffect(() => {
    if (queryMode === "range" && trendCode) {
      loadTrendData();
    }
  }, [trendCode, queryMode]);

  const handleSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      const res = await triggerSectorSnapshot();
      if (res.success) {
        message.success(`快照成功：行业 ${res.industry_count} 个，概念 ${res.concept_count} 个`);
        loadDates();
        if (queryMode === "single") loadSingleData();
        else loadRangeData();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("快照请求失败");
    } finally {
      setSnapshotLoading(false);
    }
  };

  const handleQuery = () => {
    if (queryMode === "single") loadSingleData();
    else loadRangeData();
  };

  const sectorOptions = sectorType === "industry" ? "行业板块" : "概念板块";

  // ── Render single-day mode ──
  const renderSingleMode = () => {
    if (!singleData) {
      return availableDates.length === 0 ? (
        <Empty description="暂无历史数据，请先进行数据快照">
          <Button type="primary" onClick={handleSnapshot} loading={snapshotLoading}>
            立即快照
          </Button>
        </Empty>
      ) : null;
    }

    const items = [...singleData.items].sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0));
    const flowSorted = [...singleData.items].sort(
      (a, b) => (b.main_net_inflow ?? 0) - (a.main_net_inflow ?? 0)
    );

    const tabItems = [
      {
        key: "trend",
        label: "涨跌排名",
        children: (
          <>
            <ReactECharts
              option={buildTrendBarChart(items)}
              style={{ height: 320, marginBottom: 16 }}
              notMerge
              lazyUpdate
            />
            <Table
              dataSource={items}
              columns={singleDayColumns}
              rowKey="code"
              size="small"
              pagination={{ pageSize: 15, showSizeChanger: false }}
              scroll={{ x: 900 }}
            />
          </>
        ),
      },
      {
        key: "flow",
        label: "资金流向",
        children: (
          <>
            <ReactECharts
              option={buildFlowBarChart(flowSorted)}
              style={{ height: 320, marginBottom: 16 }}
              notMerge
              lazyUpdate
            />
            <Table
              dataSource={flowSorted}
              columns={singleDayColumns}
              rowKey="code"
              size="small"
              pagination={{ pageSize: 15, showSizeChanger: false }}
              scroll={{ x: 900 }}
            />
          </>
        ),
      },
    ];

    return (
      <Tabs
        activeKey={singleTab}
        onChange={setSingleTab}
        items={tabItems}
      />
    );
  };

  // ── Render range mode ──
  const renderRangeMode = () => {
    if (!rangeData || rangeData.sectors.length === 0) {
      return availableDates.length === 0 ? (
        <Empty description="暂无历史数据，请先进行数据快照">
          <Button type="primary" onClick={handleSnapshot} loading={snapshotLoading}>
            立即快照
          </Button>
        </Empty>
      ) : (
        <Empty description="该时间范围内无数据" />
      );
    }

    const sectors = rangeData.sectors;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {/* Aggregated bar chart */}
        <div>
          <Typography.Title level={5}>平均涨跌幅排名（前10 + 后10）</Typography.Title>
          <ReactECharts
            option={buildRangeBarChart(sectors)}
            style={{ height: 360 }}
            notMerge
            lazyUpdate
          />
        </div>

        {/* Trend line chart */}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              单板块趋势
            </Typography.Title>
            <Select
              value={trendCode || undefined}
              placeholder="选择板块"
              style={{ width: 200 }}
              showSearch
              optionFilterProp="label"
              onChange={(v) => setTrendCode(v)}
              options={sectors.slice(0, 50).map((s) => ({
                value: s.code,
                label: s.name,
              }))}
            />
          </div>
          {trendData && trendData.data.length > 0 ? (
            <ReactECharts
              option={buildTrendLineChart(trendData)}
              style={{ height: 360 }}
              notMerge
              lazyUpdate
            />
          ) : trendCode ? (
            <Empty description="该板块在此时间范围内无数据" />
          ) : (
            <Empty description="请选择一个板块查看趋势" />
          )}
        </div>

        {/* Summary table */}
        <div>
          <Typography.Title level={5}>区间统计汇总</Typography.Title>
          <Table
            dataSource={sectors}
            columns={rangeColumns}
            rowKey="code"
            size="small"
            pagination={{ pageSize: 15, showSizeChanger: false }}
            scroll={{ x: 800 }}
          />
        </div>
      </div>
    );
  };

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
          历史板块
        </Typography.Title>
        <Button
          icon={<CameraOutlined />}
          onClick={handleSnapshot}
          loading={snapshotLoading}
          size="small"
        >
          立即快照
        </Button>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <Segmented
          options={[
            { label: "单日查询", value: "single" },
            { label: "区间统计", value: "range" },
          ]}
          value={queryMode}
          onChange={(v) => setQueryMode(v as QueryMode)}
        />
        <Segmented
          options={[
            { label: "行业板块", value: "industry" },
            { label: "概念板块", value: "concept" },
          ]}
          value={sectorType}
          onChange={(v) => {
            setSectorType(v as SectorType);
            setSingleData(null);
            setRangeData(null);
            setTrendData(null);
            setTrendCode("");
          }}
        />
        {queryMode === "single" ? (
          <DatePicker
            value={dayjs(selectedDate)}
            onChange={(d) => d && setSelectedDate(d.format("YYYY-MM-DD"))}
            allowClear={false}
          />
        ) : (
          <RangePicker
            value={[dayjs(dateRange[0]), dayjs(dateRange[1])]}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setDateRange([dates[0].format("YYYY-MM-DD"), dates[1].format("YYYY-MM-DD")]);
              }
            }}
          />
        )}
        <Button
          type="primary"
          icon={<SyncOutlined spin={loading} />}
          onClick={handleQuery}
          loading={loading}
          size="small"
        >
          查询
        </Button>
      </div>

      {error && (
        <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}

      <Spin spinning={loading}>
        {queryMode === "single" ? renderSingleMode() : renderRangeMode()}
      </Spin>
    </div>
  );
}
