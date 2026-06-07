import { useState, useCallback } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Table,
  Tag,
  Space,
  Card,
  Row,
  Col,
  Statistic,
} from "antd";
import { SyncOutlined, HistoryOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { fetchRecommendationHistory } from "../../api/stock";
import StockLink from "../../components/StockLink";
import type { RecommendationListResponse, RecommendationItem } from "../../types";

const POSITIVE_COLOR = "#cf1322";
const NEGATIVE_COLOR = "#3f8600";

function fmtPct(v: number | null): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

const riskColors: Record<string, string> = {
  low: "green",
  medium: "orange",
  high: "red",
};

const columns = [
  { title: "日期", dataIndex: "trade_date", key: "trade_date", width: 110 },
  {
    title: "代码",
    dataIndex: "code",
    key: "code",
    width: 90,
    render: (v: string, r: RecommendationItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
  },
  { title: "名称", dataIndex: "name", key: "name", width: 100 },
  { title: "行业", dataIndex: "sector", key: "sector", width: 100 },
  {
    title: "风险",
    dataIndex: "risk_level",
    key: "risk_level",
    width: 70,
    render: (v: string) => <Tag color={riskColors[v] || "default"}>{v}</Tag>,
  },
  {
    title: "信心度",
    dataIndex: "confidence",
    key: "confidence",
    width: 90,
    render: (v: number) => `${Math.round(v * 100)}%`,
  },
  {
    title: "评分",
    dataIndex: "score",
    key: "score",
    width: 60,
    render: (v: number) => v.toFixed(1),
  },
  {
    title: "实际收益",
    dataIndex: "actual_return_pct",
    key: "actual_return_pct",
    width: 100,
    sorter: (a: RecommendationItem, b: RecommendationItem) => (a.actual_return_pct ?? 0) - (b.actual_return_pct ?? 0),
    render: (v: number | null) =>
      v != null ? (
        <span style={{ color: v > 0 ? POSITIVE_COLOR : v < 0 ? NEGATIVE_COLOR : undefined, fontWeight: "bold" }}>
          {fmtPct(v)}
        </span>
      ) : "--",
  },
  {
    title: "状态",
    dataIndex: "status",
    key: "status",
    width: 80,
    render: (v: string) => {
      const colorMap: Record<string, string> = { pending: "blue", completed: "green", expired: "default" };
      return <Tag color={colorMap[v] || "default"}>{v}</Tag>;
    },
  },
  {
    title: "推荐理由",
    dataIndex: "reason",
    key: "reason",
    ellipsis: true,
  },
];

function dailyChartOption(items: RecommendationItem[]) {
  const dailyMap: Record<string, { count: number; returns: number[] }> = {};
  for (const item of items) {
    const d = item.trade_date;
    if (!dailyMap[d]) dailyMap[d] = { count: 0, returns: [] };
    dailyMap[d].count++;
    if (item.actual_return_pct != null) dailyMap[d].returns.push(item.actual_return_pct);
  }

  const dates = Object.keys(dailyMap).sort();
  const counts = dates.map((d) => dailyMap[d].count);
  const avgReturns = dates.map((d) => {
    const rs = dailyMap[d].returns;
    return rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 0;
  });

  return {
    tooltip: { trigger: "axis" as const },
    legend: { data: ["推荐数量", "平均收益"] },
    grid: { left: 60, right: 60, top: 40, bottom: 30 },
    xAxis: { type: "category" as const, data: dates },
    yAxis: [
      { type: "value" as const, name: "推荐数量" },
      { type: "value" as const, name: "平均收益(%)", axisLabel: { formatter: (v: number) => `${v}%` } },
    ],
    series: [
      { name: "推荐数量", type: "bar" as const, data: counts, itemStyle: { color: "#1890ff" } },
      {
        name: "平均收益",
        type: "line" as const,
        yAxisIndex: 1,
        data: avgReturns.map((v) => +v.toFixed(2)),
        itemStyle: { color: POSITIVE_COLOR },
      },
    ],
  };
}

export default function StockHistory() {
  const [data, setData] = useState<RecommendationListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const loadData = useCallback(async (p = 1) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRecommendationHistory(50, (p - 1) * 50);
      setData(res);
    } catch {
      setError("获取历史推荐数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    loadData(next);
  };

  const items = data?.items ?? [];
  const withReturn = items.filter((i) => i.actual_return_pct != null);
  const hitRate = withReturn.length ? (withReturn.filter((i) => (i.actual_return_pct ?? 0) > 0).length / withReturn.length * 100).toFixed(1) : "--";
  const avgReturn = withReturn.length ? (withReturn.reduce((s, i) => s + (i.actual_return_pct ?? 0), 0) / withReturn.length).toFixed(2) : "--";
  const bestReturn = withReturn.length ? Math.max(...withReturn.map((i) => i.actual_return_pct ?? 0)).toFixed(2) : "--";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>历史推荐</Typography.Title>
        <Button icon={<SyncOutlined spin={loading} />} onClick={() => loadData(page)} size="small">刷新</Button>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="总推荐数" value={data?.total ?? 0} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="命中率" value={hitRate} suffix="%" valueStyle={{ color: Number(hitRate) >= 50 ? POSITIVE_COLOR : NEGATIVE_COLOR }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="平均收益" value={avgReturn} suffix="%" valueStyle={{ color: Number(avgReturn) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="最佳收益" value={bestReturn} suffix="%" valueStyle={{ color: POSITIVE_COLOR }} /></Card>
        </Col>
      </Row>

      <Spin spinning={loading && !data}>
        {items.length > 0 && (
          <ReactECharts option={dailyChartOption(items)} style={{ height: 280, marginBottom: 16 }} notMerge lazyUpdate />
        )}
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
          scroll={{ x: 1100 }}
        />
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <Space>
            <span style={{ color: "#999" }}>已加载 {items.length} / {data?.total ?? 0}</span>
            {items.length < (data?.total ?? 0) && (
              <Button icon={<HistoryOutlined />} onClick={loadMore} size="small">加载更多</Button>
            )}
          </Space>
        </div>
      </Spin>
    </div>
  );
}
