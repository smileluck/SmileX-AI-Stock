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
  Tag,
} from "antd";
import {
  SyncOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from "@ant-design/icons";
import { fetchStockOverview } from "../../api/stock";
import StockLink from "../../components/StockLink";
import type { StockOverviewResponse, StockHotItem, HotStockSource, HotConceptItem, DrivingConcept } from "../../types";

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

function fmtVolume(v: number | null): string {
  if (v == null) return "--";
  if (v >= 1_0000_0000) return (v / 1_0000_0000).toFixed(2) + "亿股";
  if (v >= 1_0000) return (v / 1_0000).toFixed(2) + "万股";
  return v.toLocaleString() + "股";
}

const hotColumns = [
  {
    title: "排名",
    width: 50,
    render: (_: unknown, __: unknown, idx: number) => idx + 1,
  },
  {
    title: "代码",
    dataIndex: "code",
    key: "code",
    width: 80,
    render: (v: string, r: StockHotItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
  },
  { title: "名称", dataIndex: "name", key: "name", width: 90, ellipsis: true },
  {
    title: "最新价",
    dataIndex: "price",
    key: "price",
    width: 80,
    render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
  },
  {
    title: "涨跌幅",
    dataIndex: "change_pct",
    key: "change_pct",
    width: 80,
    sorter: (a: StockHotItem, b: StockHotItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
    defaultSortOrder: "descend" as const,
    render: (v: number | null) => <span style={{ color: pctColor(v), fontWeight: "bold" }}>{fmtPct(v)}</span>,
  },
  {
    title: "成交额",
    dataIndex: "amount",
    key: "amount",
    width: 90,
    sorter: (a: StockHotItem, b: StockHotItem) => (a.amount ?? 0) - (b.amount ?? 0),
    render: (v: number | null) => fmtAmount(v),
  },
  {
    title: "成交量",
    dataIndex: "volume",
    key: "volume",
    width: 90,
    sorter: (a: StockHotItem, b: StockHotItem) => (a.volume ?? 0) - (b.volume ?? 0),
    render: (v: number | null) => fmtVolume(v),
  },
  {
    title: "受力分析",
    dataIndex: "driving_concepts",
    key: "driving_concepts",
    width: 180,
    render: (v: DrivingConcept[]) => {
      if (!v || v.length === 0) return <span style={{ color: "#999" }}>--</span>;
      return (
        <span style={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
          {v.map((c) => (
            <Tag key={c.name} color={c.change_pct > 0 ? "red" : c.change_pct < 0 ? "green" : "default"} style={{ fontSize: 11, margin: 0 }}>
              {c.name} {c.change_pct > 0 ? "+" : ""}{c.change_pct.toFixed(2)}%
            </Tag>
          ))}
        </span>
      );
    },
  },
  {
    title: "所属板块",
    dataIndex: "concepts",
    key: "concepts",
    width: 200,
    render: (v: string[]) => {
      if (!v || v.length === 0) return <span style={{ color: "#999" }}>--</span>;
      return (
        <span style={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
          {v.map((c) => (
            <Tag key={c} style={{ fontSize: 11, margin: 0 }}>{c}</Tag>
          ))}
        </span>
      );
    },
  },
];

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
  const hotSources: HotStockSource[] = s?.hot_stocks ?? [];
  const hotConcepts: HotConceptItem[] = s?.hot_concepts ?? [];
  const topConcepts = hotConcepts.filter((c) => c.sector_type === "concept").slice(0, 5);
  const topIndustries = hotConcepts.filter((c) => c.sector_type === "industry").slice(0, 5);

  const hotTabItems = hotSources.length > 0
    ? hotSources.map((src) => ({
        key: `hot_${src.source}`,
        label: src.source,
        children: (
          <Table
            dataSource={src.items}
            columns={hotColumns}
            rowKey="code"
            size="small"
            pagination={{ pageSize: 15, showSizeChanger: false }}
          />
        ),
      }))
    : [{ key: "hot_empty", label: "热门个股", children: <div style={{ color: "#999", textAlign: "center", padding: 24 }}>暂无数据</div> }];

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

        {/* Hot Concepts / Industries */}
        {hotConcepts.length > 0 && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Card size="small" title="热门概念" bodyStyle={{ padding: "8px 12px" }}>
                {topConcepts.map((c) => (
                  <div key={c.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0" }}>
                    <span>
                      <Tag color="blue">{c.name}</Tag>
                      <span style={{ color: pctColor(c.change_pct), fontWeight: "bold", fontSize: 13 }}>{fmtPct(c.change_pct)}</span>
                    </span>
                    <span style={{ color: "#999", fontSize: 12 }}>
                      {c.leading_stock && c.leading_stock_code ? (
                        <>领涨: <StockLink code={c.leading_stock_code} name={c.leading_stock}>{c.leading_stock}</StockLink>
                          {c.leading_stock_change_pct != null && (
                            <span style={{ color: pctColor(c.leading_stock_change_pct), marginLeft: 4 }}>{fmtPct(c.leading_stock_change_pct)}</span>
                          )}
                        </>
                      ) : c.main_net_inflow != null ? (
                        <>资金: <span style={{ color: pctColor(c.main_net_inflow) }}>{fmtAmount(c.main_net_inflow)}</span></>
                      ) : null}
                    </span>
                  </div>
                ))}
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title="热门行业" bodyStyle={{ padding: "8px 12px" }}>
                {topIndustries.map((c) => (
                  <div key={c.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0" }}>
                    <span>
                      <Tag color="green">{c.name}</Tag>
                      <span style={{ color: pctColor(c.change_pct), fontWeight: "bold", fontSize: 13 }}>{fmtPct(c.change_pct)}</span>
                    </span>
                    <span style={{ color: "#999", fontSize: 12 }}>
                      领涨: {c.leading_stock_code ? <StockLink code={c.leading_stock_code} name={c.leading_stock}>{c.leading_stock}</StockLink> : c.leading_stock}
                      {c.leading_stock_change_pct != null && (
                        <span style={{ color: pctColor(c.leading_stock_change_pct), marginLeft: 4 }}>{fmtPct(c.leading_stock_change_pct)}</span>
                      )}
                    </span>
                  </div>
                ))}
              </Card>
            </Col>
          </Row>
        )}

        <Tabs defaultActiveKey={hotTabItems[0]?.key} items={hotTabItems} />
      </Spin>
    </div>
  );
}
