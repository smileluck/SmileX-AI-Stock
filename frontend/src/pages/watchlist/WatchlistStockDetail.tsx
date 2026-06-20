import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Table,
  Tag,
  Tabs,
  Card,
  Statistic,
  Row,
  Col,
  Timeline,
  Empty,
  Space,
} from "antd";
import { ArrowLeftOutlined, SyncOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  fetchWatchlistDaily,
  fetchWatchlistAnalysis,
} from "../../api/watchlist";
import { fetchWatchlistStocks } from "../../api/watchlist";
import type {
  WatchlistStockDailyItem,
  WatchlistAnalysisItem,
  WatchlistStockItem,
} from "../../types";
import StockLink from "../../components/StockLink";

const { Title, Text } = Typography;

const POS_COLOR = "#cf1322";
const NEG_COLOR = "#3f8600";

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "--";
  return v.toFixed(2);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null) return "--";
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + "亿";
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + "万";
  return v.toFixed(0);
}

const actionConfig: Record<string, { color: string; label: string }> = {
  buy: { color: "red", label: "建议买入" },
  wait: { color: "orange", label: "观望" },
  avoid: { color: "green", label: "回避" },
};

export default function WatchlistStockDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();

  const [daily, setDaily] = useState<WatchlistStockDailyItem[]>([]);
  const [analyses, setAnalyses] = useState<WatchlistAnalysisItem[]>([]);
  const [stockInfo, setStockInfo] = useState<WatchlistStockItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!code) return;
    setLoading(true);
    setError(null);
    try {
      const [dailyRes, analysisRes, listRes] = await Promise.all([
        fetchWatchlistDaily(code, 30),
        fetchWatchlistAnalysis({ code, limit: 50 }),
        fetchWatchlistStocks(),
      ]);
      setDaily(dailyRes);
      setAnalyses(analysisRes.items);
      const found = listRes.items.find((it) => it.code === code);
      setStockInfo(found || null);
    } catch (e) {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const chartOption = useMemo(() => {
    if (!daily.length) return {};
    const dates = daily.map((d) => d.trade_date);
    const closes = daily.map((d) => d.close);
    const highs = daily.map((d) => d.high);
    const lows = daily.map((d) => d.low);

    const addPrice = stockInfo?.add_price;
    const support = stockInfo?.latest_support;
    const resistance = stockInfo?.latest_resistance;
    const targetBuy = stockInfo?.target_buy_price;

    const markLines: any[] = [];
    if (addPrice != null) {
      markLines.push({
        yAxis: addPrice,
        name: `添加价 ${fmtPrice(addPrice)}`,
        lineStyle: { color: "#722ed1", type: "dashed", width: 1.5 },
        label: { formatter: `添加价 ${fmtPrice(addPrice)}`, position: "insideEndTop" },
      });
    }
    if (support != null) {
      markLines.push({
        yAxis: support,
        name: `支撑 ${fmtPrice(support)}`,
        lineStyle: { color: NEG_COLOR, type: "dotted" },
        label: { formatter: `支撑 ${fmtPrice(support)}`, position: "insideEndTop" },
      });
    }
    if (resistance != null) {
      markLines.push({
        yAxis: resistance,
        name: `阻力 ${fmtPrice(resistance)}`,
        lineStyle: { color: POS_COLOR, type: "dotted" },
        label: { formatter: `阻力 ${fmtPrice(resistance)}`, position: "insideEndTop" },
      });
    }
    if (targetBuy != null) {
      markLines.push({
        yAxis: targetBuy,
        name: `目标买入 ${fmtPrice(targetBuy)}`,
        lineStyle: { color: "#1890ff", type: "dashed" },
        label: { formatter: `目标买入 ${fmtPrice(targetBuy)}`, position: "insideEndTop" },
      });
    }

    return {
      tooltip: {
        trigger: "axis",
        formatter: (params: any[]) => {
          const idx = params[0]?.dataIndex;
          if (idx == null || !daily[idx]) return "";
          const d = daily[idx];
          return (
            `${d.trade_date}<br/>` +
            `开 ${fmtPrice(d.open)} 收 ${fmtPrice(d.close)}<br/>` +
            `高 ${fmtPrice(d.high)} 低 ${fmtPrice(d.low)}<br/>` +
            `涨跌 ${fmtPct(d.change_pct)} 换手 ${d.turnover_rate?.toFixed(2) ?? "--"}%<br/>` +
            `主力净流 ${fmtAmount(d.main_net_inflow)}`
          );
        },
      },
      legend: { data: ["收盘价", "最高", "最低"], top: 0 },
      grid: { left: 60, right: 30, top: 40, bottom: 60 },
      xAxis: { type: "category", data: dates },
      yAxis: { type: "value", scale: true },
      dataZoom: [{ type: "inside" }, { type: "slider" }],
      series: [
        {
          name: "收盘价",
          type: "line",
          data: closes,
          smooth: true,
          symbol: "circle",
          symbolSize: 4,
          lineStyle: { width: 2 },
          markLine: markLines.length ? { data: markLines, symbol: "none" } : undefined,
        },
        {
          name: "最高",
          type: "line",
          data: highs,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 1, opacity: 0.4, color: POS_COLOR },
        },
        {
          name: "最低",
          type: "line",
          data: lows,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 1, opacity: 0.4, color: NEG_COLOR },
        },
      ],
    };
  }, [daily, stockInfo]);

  const dailyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date", width: 110 },
    { title: "开", dataIndex: "open", key: "open", render: (v: number | null) => fmtPrice(v) },
    { title: "高", dataIndex: "high", key: "high", render: (v: number | null) => <span style={{ color: POS_COLOR }}>{fmtPrice(v)}</span> },
    { title: "低", dataIndex: "low", key: "low", render: (v: number | null) => <span style={{ color: NEG_COLOR }}>{fmtPrice(v)}</span> },
    { title: "收", dataIndex: "close", key: "close", render: (v: number | null) => fmtPrice(v) },
    {
      title: "涨跌%",
      dataIndex: "change_pct",
      key: "change_pct",
      render: (v: number | null) => (
        <span style={{ color: v == null ? "default" : v > 0 ? POS_COLOR : v < 0 ? NEG_COLOR : "default" }}>
          {fmtPct(v)}
        </span>
      ),
    },
    {
      title: "换手率",
      dataIndex: "turnover_rate",
      key: "turnover_rate",
      render: (v: number | null) => (v == null ? "--" : `${v.toFixed(2)}%`),
    },
    {
      title: "主力净流",
      dataIndex: "main_net_inflow",
      key: "main_net_inflow",
      render: (v: number | null) => (
        <span style={{ color: v == null ? "default" : v > 0 ? POS_COLOR : v < 0 ? NEG_COLOR : "default" }}>
          {fmtAmount(v)}
        </span>
      ),
    },
  ];

  const sortedAnalyses = useMemo(() => {
    return [...analyses].sort((a, b) => {
      if (a.trade_date !== b.trade_date) return b.trade_date.localeCompare(a.trade_date);
      const phaseOrder = (p: string) => (p === "close" ? 1 : 0);
      return phaseOrder(b.phase) - phaseOrder(a.phase);
    });
  }, [analyses]);

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/watchlist/stocks")}>
            返回列表
          </Button>
          <Title level={4} style={{ margin: 0 }}>
            {stockInfo?.name || code}{" "}
            {code && <StockLink code={code} name={stockInfo?.name} />}
          </Title>
        </Space>
        <Button icon={<SyncOutlined spin={loading} />} onClick={loadData}>
          刷新
        </Button>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="添加价"
                value={stockInfo?.add_price ?? null}
                precision={2}
                suffix={stockInfo?.add_date ? ` (${stockInfo.add_date})` : ""}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="当前价"
                value={stockInfo?.close ?? null}
                precision={2}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="距添加价"
                value={stockInfo?.gain_since_add_pct ?? null}
                precision={2}
                suffix="%"
                valueStyle={{
                  color:
                    (stockInfo?.gain_since_add_pct ?? 0) > 0
                      ? POS_COLOR
                      : (stockInfo?.gain_since_add_pct ?? 0) < 0
                      ? NEG_COLOR
                      : undefined,
                }}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="目标买入价" value={stockInfo?.target_buy_price ?? null} precision={2} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="止损价" value={stockInfo?.stop_loss_price ?? null} precision={2} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <div style={{ marginBottom: 4 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>最新建议</Text>
              </div>
              {stockInfo?.latest_action ? (
                <Tag color={actionConfig[stockInfo.latest_action]?.color || "default"}>
                  {actionConfig[stockInfo.latest_action]?.label || stockInfo.latest_action}
                </Tag>
              ) : (
                <Text type="secondary">--</Text>
              )}
            </Card>
          </Col>
        </Row>

        <Card title="近 30 日走势（含关键价位标注）" size="small" style={{ marginBottom: 16 }}>
          {daily.length === 0 ? (
            <Empty description="暂无历史数据，请等待快照任务执行" />
          ) : (
            <ReactECharts option={chartOption} style={{ height: 360 }} />
          )}
        </Card>

        <Tabs
          items={[
            {
              key: "daily",
              label: `每日行情 (${daily.length})`,
              children: (
                <Table
                  rowKey="trade_date"
                  dataSource={daily}
                  columns={dailyColumns}
                  pagination={{ pageSize: 15 }}
                  size="small"
                />
              ),
            },
            {
              key: "analysis",
              label: `分析历史 (${analyses.length})`,
              children:
                sortedAnalyses.length === 0 ? (
                  <Empty description="还没有分析记录" />
                ) : (
                  <Timeline
                    items={sortedAnalyses.map((a) => {
                      const cfg = actionConfig[a.suggested_action] || { color: "default", label: a.suggested_action };
                      return {
                        color:
                          a.suggested_action === "buy"
                            ? "red"
                            : a.suggested_action === "wait"
                            ? "orange"
                            : a.suggested_action === "avoid"
                            ? "green"
                            : "gray",
                        children: (
                          <div key={a.id}>
                            <div style={{ marginBottom: 4 }}>
                              <Text strong>{a.trade_date}</Text>
                              <Tag style={{ marginLeft: 8 }} color={a.phase === "morning" ? "blue" : "purple"}>
                                {a.phase === "morning" ? "早盘" : "收盘"}
                              </Tag>
                              <Tag color={cfg.color}>{cfg.label}</Tag>
                              <Text type="secondary" style={{ marginLeft: 8 }}>
                                置信度 {Math.round((a.confidence || 0) * 100)}%
                              </Text>
                            </div>
                            <div style={{ fontSize: 13, color: "#555" }}>
                              {a.reason && <div>{a.reason}</div>}
                              <Space split={<span style={{ color: "#ccc" }}>|</span>} style={{ marginTop: 4 }}>
                                {a.buy_low != null && <span>建议买入 {fmtPrice(a.buy_low)} ~ {fmtPrice(a.buy_high)}</span>}
                                {a.support_price != null && <span style={{ color: NEG_COLOR }}>支撑 {fmtPrice(a.support_price)}</span>}
                                {a.resistance_price != null && <span style={{ color: POS_COLOR }}>阻力 {fmtPrice(a.resistance_price)}</span>}
                              </Space>
                            </div>
                          </div>
                        ),
                      };
                    })}
                  />
                ),
            },
          ]}
        />
      </Spin>
    </div>
  );
}
