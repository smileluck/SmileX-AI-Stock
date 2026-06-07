import { useState, useEffect, useCallback } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Table,
  Tag,
  Progress,
  message,
  DatePicker,
} from "antd";
import { SyncOutlined, BulbOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { fetchRecommendations, triggerRecommendationGeneration } from "../../api/stock";
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
    title: "推荐理由",
    dataIndex: "reason",
    key: "reason",
    ellipsis: true,
    width: 200,
  },
  {
    title: "操作策略",
    dataIndex: "strategy",
    key: "strategy",
    width: 130,
  },
  {
    title: "目标价",
    dataIndex: "target_price",
    key: "target_price",
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "止损价",
    dataIndex: "stop_loss_price",
    key: "stop_loss_price",
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
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
    width: 100,
    sorter: (a: RecommendationItem, b: RecommendationItem) => a.confidence - b.confidence,
    render: (v: number) => <Progress percent={Math.round(v * 100)} size="small" />,
  },
  {
    title: "评分",
    dataIndex: "score",
    key: "score",
    width: 70,
    sorter: (a: RecommendationItem, b: RecommendationItem) => a.score - b.score,
    defaultSortOrder: "descend" as const,
    render: (v: number) => v.toFixed(1),
  },
  {
    title: "实际收益",
    dataIndex: "actual_return_pct",
    key: "actual_return_pct",
    width: 100,
    render: (v: number | null) =>
      v != null ? (
        <span style={{ color: v > 0 ? POSITIVE_COLOR : v < 0 ? NEGATIVE_COLOR : undefined, fontWeight: "bold" }}>
          {fmtPct(v)}
        </span>
      ) : "--",
  },
];

export default function StockRecommendation() {
  const [data, setData] = useState<RecommendationListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));

  const loadData = useCallback(async (tradeDate?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRecommendations(tradeDate || date);
      setData(res);
    } catch {
      setError("获取推荐数据失败");
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleGenerate = async () => {
    setGenLoading(true);
    try {
      const res = await triggerRecommendationGeneration();
      if (res.success) {
        message.success(`生成 ${res.total} 条推荐`);
        loadData();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成推荐失败");
    } finally {
      setGenLoading(false);
    }
  };

  const items = data?.items ?? [];
  const avgConf = items.length ? (items.reduce((s, i) => s + i.confidence, 0) / items.length * 100).toFixed(0) : "--";
  const riskDist = items.reduce<Record<string, number>>((acc, i) => { acc[i.risk_level] = (acc[i.risk_level] || 0) + 1; return acc; }, {});

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>今日推荐</Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => { const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD"); setDate(ds); }}
            size="small"
          />
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => loadData()} size="small">刷新</Button>
          <Button type="primary" icon={<BulbOutlined />} onClick={handleGenerate} loading={genLoading}>
            AI 生成推荐
          </Button>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Spin spinning={loading && !data}>
        <div style={{ marginBottom: 16, display: "flex", gap: 16, fontSize: 14, color: "#666" }}>
          <span>共 <b style={{ color: POSITIVE_COLOR }}>{items.length}</b> 条推荐</span>
          <span>平均信心度 <b>{avgConf}%</b></span>
          <span>风险分布：
            {Object.entries(riskDist).map(([k, v]) => (
              <Tag key={k} color={riskColors[k]} style={{ marginLeft: 4 }}>{k}: {v}</Tag>
            ))}
          </span>
        </div>

        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 15, showSizeChanger: false }}
          scroll={{ x: 1100 }}
        />
      </Spin>
    </div>
  );
}
