import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Table,
  Card,
  Row,
  Col,
  Statistic,
  DatePicker,
  Tabs,
  Tag,
  message,
} from "antd";
import { SyncOutlined, ThunderboltOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { fetchLimitUp, triggerLimitUpSnapshot } from "../../api/stock";
import StockLink from "../../components/StockLink";
import type { LimitUpResponse, LimitUpItem } from "../../types";

const POSITIVE_COLOR = "#cf1322";

const BOARD_LIST = ["沪深主板", "创业板", "科创板", "北交所"] as const;
const BOARD_COLORS: Record<string, string> = {
  "沪深主板": "#1677ff",
  "创业板": "#fa8c16",
  "科创板": "#722ed1",
  "北交所": "#13c2c2",
};

function classifyBoard(code: string): string {
  if (code.startsWith("688")) return "科创板";
  if (code.startsWith("60") || code.startsWith("00")) return "沪深主板";
  if (code.startsWith("30")) return "创业板";
  if (code.startsWith("8") || code.startsWith("4")) return "北交所";
  return "其他";
}

function fmtAmount(v: number | null): string {
  if (v == null) return "--";
  if (Math.abs(v) >= 1_0000_0000) return (v / 1_0000_0000).toFixed(2) + "亿";
  if (Math.abs(v) >= 1_0000) return (v / 1_0000).toFixed(2) + "万";
  return v.toLocaleString();
}

function fmtPct(v: number | null): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

const columns = [
  {
    title: "代码",
    dataIndex: "code",
    key: "code",
    width: 90,
    render: (v: string, r: LimitUpItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
  },
  { title: "名称", dataIndex: "name", key: "name", width: 100 },
  {
    title: "板块",
    dataIndex: "board",
    key: "board",
    width: 90,
    render: (v: string) => (
      <Tag color={BOARD_COLORS[v] || "default"} style={{ margin: 0 }}>{v || "其他"}</Tag>
    ),
  },
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
    sorter: (a: LimitUpItem, b: LimitUpItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => <span style={{ color: POSITIVE_COLOR }}>{fmtPct(v)}</span>,
  },
  {
    title: "换手率",
    dataIndex: "turnover_rate",
    key: "turnover_rate",
    sorter: (a: LimitUpItem, b: LimitUpItem) => (a.turnover_rate ?? 0) - (b.turnover_rate ?? 0),
    render: (v: number | null) => (v != null ? `${v.toFixed(2)}%` : "--"),
  },
  {
    title: "成交额",
    dataIndex: "amount",
    key: "amount",
    sorter: (a: LimitUpItem, b: LimitUpItem) => (a.amount ?? 0) - (b.amount ?? 0),
    render: (v: number | null) => fmtAmount(v),
  },
  {
    title: "振幅",
    dataIndex: "amplitude",
    key: "amplitude",
    render: (v: number | null) => (v != null ? `${v.toFixed(2)}%` : "--"),
  },
  {
    title: "首次封板",
    dataIndex: "first_limit_up_time",
    key: "first_limit_up_time",
    width: 100,
  },
  {
    title: "最后封板",
    dataIndex: "last_limit_up_time",
    key: "last_limit_up_time",
    width: 100,
  },
  {
    title: "连板",
    dataIndex: "limit_up_times",
    key: "limit_up_times",
    sorter: (a: LimitUpItem, b: LimitUpItem) => a.limit_up_times - b.limit_up_times,
    render: (v: number) => (v > 1 ? <span style={{ color: POSITIVE_COLOR, fontWeight: "bold" }}>{v}</span> : v),
  },
  { title: "行业", dataIndex: "sector", key: "sector", width: 100 },
];

function sectorChart(items: LimitUpItem[]) {
  const sectorMap: Record<string, number> = {};
  for (const item of items) {
    const s = item.sector || "其他";
    sectorMap[s] = (sectorMap[s] || 0) + 1;
  }
  const sorted = Object.entries(sectorMap).sort((a, b) => b[1] - a[1]).slice(0, 20);

  return {
    tooltip: { trigger: "axis" as const },
    grid: { left: 100, right: 20, top: 10, bottom: 30 },
    xAxis: { type: "value" as const },
    yAxis: { type: "category" as const, data: sorted.map(([name]) => name).reverse() },
    series: [{
      type: "bar" as const,
      data: sorted.map(([, count]) => count).reverse(),
      itemStyle: { color: POSITIVE_COLOR },
    }],
  };
}

function boardChart(boardStats: Record<string, number>) {
  const boards = BOARD_LIST.filter((b) => boardStats[b]);
  return {
    tooltip: { trigger: "item" as const },
    legend: { bottom: 0 },
    series: [{
      type: "pie" as const,
      radius: ["40%", "70%"],
      avoidLabelOverlap: false,
      label: { show: true, formatter: "{b}: {c}只" },
      data: boards.map((b) => ({ name: b, value: boardStats[b] || 0, itemStyle: { color: BOARD_COLORS[b] } })),
    }],
  };
}

export default function StockLimitUp() {
  const [data, setData] = useState<LimitUpResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [snapLoading, setSnapLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [activeBoard, setActiveBoard] = useState<string>("all");

  const loadData = useCallback(async (tradeDate?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLimitUp(tradeDate || date);
      setData(res);
    } catch {
      setError("获取涨停数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSnapshot = async () => {
    setSnapLoading(true);
    try {
      const res = await triggerLimitUpSnapshot();
      if (res.success) {
        message.success(res.message);
        loadData();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("触发快照失败");
    } finally {
      setSnapLoading(false);
    }
  };

  const allItems = useMemo(() => {
    const raw = data?.items ?? [];
    return raw.map((item) => ({
      ...item,
      board: item.board || classifyBoard(item.code),
    }));
  }, [data]);

  const boardStats = useMemo(() => {
    const stats: Record<string, number> = {};
    for (const item of allItems) {
      const b = item.board || "其他";
      stats[b] = (stats[b] || 0) + 1;
    }
    return stats;
  }, [allItems]);

  const filteredItems = useMemo(() => {
    if (activeBoard === "all") return allItems;
    return allItems.filter((item) => item.board === activeBoard);
  }, [allItems, activeBoard]);

  const avgTurnover = filteredItems.length
    ? (filteredItems.reduce((s, i) => s + (i.turnover_rate ?? 0), 0) / filteredItems.length).toFixed(2)
    : "--";
  const maxBoard = filteredItems.length ? Math.max(...filteredItems.map((i) => i.limit_up_times)) : 0;
  const totalAmount = filteredItems.reduce((s, i) => s + (i.amount ?? 0), 0);

  const tabItems = [
    { key: "all", label: `全部 (${allItems.length})` },
    ...BOARD_LIST.map((b) => ({
      key: b,
      label: `${b} (${boardStats[b] || 0})`,
    })),
  ].filter((t) => t.key === "all" || (boardStats[t.key] || 0) > 0);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>今日涨停</Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => { const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD"); setDate(ds); }}
            size="small"
          />
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => loadData()} size="small">刷新</Button>
          <Button icon={<ThunderboltOutlined />} onClick={handleSnapshot} loading={snapLoading} size="small">快照</Button>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="涨停数量" value={filteredItems.length} valueStyle={{ color: POSITIVE_COLOR }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="平均换手率" value={avgTurnover} suffix="%" /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="总成交额" value={fmtAmount(totalAmount)} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="最高连板" value={maxBoard} valueStyle={maxBoard > 1 ? { color: POSITIVE_COLOR, fontWeight: "bold" } : undefined} /></Card>
        </Col>
      </Row>

      <Spin spinning={loading && !data}>
        {allItems.length > 0 && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={10}>
              <ReactECharts option={boardChart(boardStats)} style={{ height: 280 }} notMerge lazyUpdate />
            </Col>
            <Col span={14}>
              <ReactECharts option={sectorChart(filteredItems)} style={{ height: 280 }} notMerge lazyUpdate />
            </Col>
          </Row>
        )}

        <Tabs
          activeKey={activeBoard}
          onChange={setActiveBoard}
          items={tabItems}
          size="small"
          style={{ marginBottom: 0 }}
        />

        <Table
          dataSource={filteredItems}
          columns={columns}
          rowKey="code"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1200 }}
        />
      </Spin>
    </div>
  );
}
