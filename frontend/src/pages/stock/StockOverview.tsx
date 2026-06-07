import { useState, useEffect, useCallback } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Tabs,
  Table,
  Card,
  Row,
  Col,
  Statistic,
} from "antd";
import {
  SyncOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { fetchStockOverview } from "../../api/stock";
import StockLink from "../../components/StockLink";
import type { StockOverviewResponse, LimitUpItem, StockHotItem } from "../../types";

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

const hotColumns = [
  {
    title: "排名",
    width: 60,
    render: (_: unknown, __: unknown, idx: number) => idx + 1,
  },
  {
    title: "代码",
    dataIndex: "code",
    key: "code",
    width: 90,
    render: (v: string, r: StockHotItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
  },
  { title: "名称", dataIndex: "name", key: "name", width: 100 },
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
    sorter: (a: StockHotItem, b: StockHotItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
  },
  {
    title: "换手率",
    dataIndex: "turnover_rate",
    key: "turnover_rate",
    render: (v: number | null) => (v != null ? `${v.toFixed(2)}%` : "--"),
  },
  {
    title: "成交额",
    dataIndex: "amount",
    key: "amount",
    render: (v: number | null) => fmtAmount(v),
  },
];

const limitUpColumns = [
  {
    title: "代码",
    dataIndex: "code",
    key: "code",
    width: 90,
    render: (v: string, r: LimitUpItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
  },
  { title: "名称", dataIndex: "name", key: "name", width: 100 },
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
    render: (v: number | null) => <span style={{ color: pctColor(v) }}>{fmtPct(v)}</span>,
  },
  {
    title: "换手率",
    dataIndex: "turnover_rate",
    key: "turnover_rate",
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
    title: "连板数",
    dataIndex: "limit_up_times",
    key: "limit_up_times",
    sorter: (a: LimitUpItem, b: LimitUpItem) => a.limit_up_times - b.limit_up_times,
    render: (v: number) => (v > 1 ? <span style={{ color: POSITIVE_COLOR, fontWeight: "bold" }}>{v}</span> : v),
  },
  { title: "行业", dataIndex: "sector", key: "sector", width: 100 },
];

function sectorChartOption(items: LimitUpItem[]) {
  const sectorMap: Record<string, number> = {};
  for (const item of items) {
    const s = item.sector || "其他";
    sectorMap[s] = (sectorMap[s] || 0) + 1;
  }
  const sorted = Object.entries(sectorMap).sort((a, b) => b[1] - a[1]).slice(0, 15);

  return {
    tooltip: { trigger: "axis" as const },
    grid: { left: 100, right: 20, top: 10, bottom: 30 },
    xAxis: { type: "value" as const },
    yAxis: { type: "category" as const, data: sorted.map(([name]) => name).reverse(), inverse: true },
    series: [{
      type: "bar" as const,
      data: sorted.map(([, count]) => count).reverse(),
      itemStyle: { color: POSITIVE_COLOR },
    }],
  };
}

export default function StockOverview() {
  const [data, setData] = useState<StockOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchStockOverview();
      setData(res);
    } catch {
      setError("获取个股总览数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 30_000);
    return () => clearInterval(timer);
  }, [loadData]);

  const s = data?.sentiment;
  const lu = data?.limit_up;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>个股分析总览</Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {data?.fetch_time && <span style={{ fontSize: 12, color: "#999" }}>更新于 {data.fetch_time}</span>}
          <Button icon={<SyncOutlined spin={loading} />} onClick={loadData} size="small">刷新</Button>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Spin spinning={loading && !data}>
        {/* Sentiment Stats */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small"><Statistic title="上涨" value={s?.up_count ?? 0} valueStyle={{ color: POSITIVE_COLOR }} prefix={<ArrowUpOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="下跌" value={s?.down_count ?? 0} valueStyle={{ color: NEGATIVE_COLOR }} prefix={<ArrowDownOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="平盘" value={s?.flat_count ?? 0} prefix={<MinusOutlined />} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="涨停" value={s?.limit_up_count ?? 0} valueStyle={{ color: POSITIVE_COLOR }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small"><Statistic title="跌停" value={s?.limit_down_count ?? 0} valueStyle={{ color: NEGATIVE_COLOR }} /></Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="情绪评分"
                value={s?.sentiment_score ?? "--"}
                suffix={s?.sentiment_score != null ? "%" : ""}
                valueStyle={{ color: (s?.sentiment_score ?? 0) >= 50 ? POSITIVE_COLOR : NEGATIVE_COLOR }}
              />
            </Card>
          </Col>
        </Row>

        <Tabs defaultActiveKey="hot" items={[
          {
            key: "hot",
            label: "热门个股",
            children: (
              <Table
                dataSource={s?.hot_stocks ?? []}
                columns={hotColumns}
                rowKey="code"
                size="small"
                pagination={{ pageSize: 15, showSizeChanger: false }}
              />
            ),
          },
          {
            key: "limitup",
            label: `涨停概览 (${lu?.item_count ?? 0})`,
            children: (
              <>
                {lu && lu.items.length > 0 && (
                  <ReactECharts option={sectorChartOption(lu.items)} style={{ height: 300, marginBottom: 16 }} notMerge lazyUpdate />
                )}
                <Table
                  dataSource={lu?.items ?? []}
                  columns={limitUpColumns}
                  rowKey="code"
                  size="small"
                  pagination={{ pageSize: 15, showSizeChanger: false }}
                  scroll={{ x: 800 }}
                />
              </>
            ),
          },
        ]} />
      </Spin>
    </div>
  );
}
