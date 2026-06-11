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
  Tabs,
  Dropdown,
  Space,
} from "antd";
import { SyncOutlined, BulbOutlined, DownOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { fetchRecommendations, refreshRecommendationPrices, triggerRecommendationGeneration } from "../../api/stock";
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
    title: "当前价",
    dataIndex: "current_price",
    key: "current_price",
    width: 80,
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "买入区间",
    key: "buy_range",
    width: 120,
    render: (_: unknown, r: RecommendationItem) =>
      r.buy_low != null && r.buy_high != null
        ? `${r.buy_low.toFixed(2)} ~ ${r.buy_high.toFixed(2)}`
        : "--",
  },
  {
    title: "目标价",
    dataIndex: "target_price",
    key: "target_price",
    width: 80,
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "止损价",
    dataIndex: "stop_loss_price",
    key: "stop_loss_price",
    width: 80,
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "止盈价",
    dataIndex: "take_profit_price",
    key: "take_profit_price",
    width: 80,
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
  const [priceLoading, setPriceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [phase, setPhase] = useState<string>("morning");

  const loadData = useCallback(async (tradeDate?: string, p?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRecommendations(tradeDate || date, p || phase);
      setData(res);
    } catch {
      setError("获取推荐数据失败");
    } finally {
      setLoading(false);
    }
  }, [date, phase]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleGenerate = async (targetPhase: string) => {
    setGenLoading(true);
    try {
      const res = await triggerRecommendationGeneration(date, targetPhase);
      if (res.success) {
        const phaseLabels: Record<string, string> = { morning: "早盘", midday: "午盘", review: "收盘复盘", afternoon: "午后" };
        message.success(`${phaseLabels[targetPhase] || targetPhase}推荐生成 ${res.total} 条`);
        setPhase(targetPhase);
        loadData(undefined, targetPhase);
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成推荐失败");
    } finally {
      setGenLoading(false);
    }
  };

  const handlePhaseChange = (key: string) => {
    setPhase(key);
  };

  const handleRefreshPrices = async () => {
    setPriceLoading(true);
    try {
      const res = await refreshRecommendationPrices(date, phase);
      setData(res);
      message.success(`已刷新 ${res.total} 条实时行情`);
    } catch {
      message.error("刷新实时行情失败");
    } finally {
      setPriceLoading(false);
    }
  };

  const items = data?.items ?? [];
  const avgConf = items.length ? (items.reduce((s, i) => s + i.confidence, 0) / items.length * 100).toFixed(0) : "--";
  const riskDist = items.reduce<Record<string, number>>((acc, i) => { acc[i.risk_level] = (acc[i.risk_level] || 0) + 1; return acc; }, {});

  const genMenuItems = [
    { key: "morning", label: "生成早盘推荐" },
    { key: "midday", label: "生成午盘推荐" },
    { key: "review", label: "生成收盘复盘" },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Typography.Title level={4} style={{ margin: 0 }}>AI 个股推荐</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            自动生成：早盘 9:26 / 午盘 11:25 / 收盘复盘 15:35
          </Typography.Text>
        </Space>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => { const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD"); setDate(ds); }}
            size="small"
          />
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => loadData()} size="small">刷新</Button>
          <Button icon={<SyncOutlined spin={priceLoading} />} loading={priceLoading} onClick={handleRefreshPrices} size="small">
            刷新行情/实时收益
          </Button>
          <Dropdown
            menu={{ items: genMenuItems, onClick: ({ key }) => handleGenerate(key) }}
          >
            <Button type="primary" icon={<BulbOutlined />} loading={genLoading}>
              AI 生成推荐 <DownOutlined />
            </Button>
          </Dropdown>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Tabs
        activeKey={phase}
        onChange={handlePhaseChange}
        items={[
          { key: "morning", label: "早盘推荐" },
          { key: "midday", label: "午盘推荐" },
          { key: "review", label: "收盘复盘" },
        ]}
      />

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
