import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
  Radio,
  Progress,
  Tooltip,
  message,
} from "antd";
import { SyncOutlined, ThunderboltOutlined, CameraOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import {
  fetchLimitUpAnalysis,
  triggerLimitUpAnalysisSnapshot,
  triggerLimitUpAnalysisGenerate,
  fetchLimitUpAnalysisTaskStatus,
  type LimitUpAnalysisTaskStatus,
} from "../../api/limitUpAnalysis";
import StockLink from "../../components/StockLink";
import type { LimitUpAnalysisItem } from "../../types";

const POSITIVE_COLOR = "#cf1322";

const BOARD_LIST = ["沪深主板", "创业板", "科创板", "北交所"] as const;
const BOARD_COLORS: Record<string, string> = {
  "沪深主板": "#1677ff",
  "创业板": "#fa8c16",
  "科创板": "#722ed1",
  "北交所": "#13c2c2",
};

const PROB_COLORS: Record<string, string> = {
  high: "#cf1322",
  medium: "#fa8c16",
  low: "#52c41a",
};
const PROB_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

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

function parseKeyFactors(v: string | string[]): string[] {
  if (Array.isArray(v)) return v;
  try {
    return JSON.parse(v);
  } catch {
    return v ? [v] : [];
  }
}

export default function LimitUpAnalysis() {
  const [items, setItems] = useState<LimitUpAnalysisItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [snapLoading, setSnapLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [activeBoard, setActiveBoard] = useState<string>("all");
  const [activeType, setActiveType] = useState<string>("all");
  const [activePhase, setActivePhase] = useState<string>("close");
  const [taskStatus, setTaskStatus] = useState<LimitUpAnalysisTaskStatus | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollTaskAndData = useCallback(async (tradeDate: string, phase: string) => {
    try {
      const [statusRes, dataRes] = await Promise.all([
        fetchLimitUpAnalysisTaskStatus(tradeDate, phase),
        fetchLimitUpAnalysis(tradeDate, undefined, undefined, phase),
      ]);
      setTaskStatus(statusRes);
      setItems(dataRes.items || []);
      if (!statusRes.active) {
        stopPolling();
        setGenLoading(false);
        if (statusRes.done > 0 && statusRes.done >= statusRes.total) {
          message.success(`AI分析完成：${statusRes.done}/${statusRes.total}`);
        }
      }
    } catch {
      // ignore transient poll errors, keep polling
    }
  }, [stopPolling]);

  const startPolling = useCallback((tradeDate: string, phase: string) => {
    stopPolling();
    pollTimerRef.current = setInterval(() => {
      pollTaskAndData(tradeDate, phase);
    }, 5000);
  }, [stopPolling, pollTaskAndData]);

  const loadData = useCallback(async (tradeDate?: string, phase?: string) => {
    setLoading(true);
    setError(null);
    const td = tradeDate || date;
    const ph = phase || activePhase;
    try {
      const [dataRes, statusRes] = await Promise.all([
        fetchLimitUpAnalysis(td, undefined, undefined, ph),
        fetchLimitUpAnalysisTaskStatus(td, ph),
      ]);
      setItems(dataRes.items || []);
      setTaskStatus(statusRes);
      if (statusRes.active) {
        setGenLoading(true);
        startPolling(td, ph);
      } else {
        setGenLoading(false);
        stopPolling();
      }
    } catch {
      setError("获取涨停分析数据失败，请检查后端服务是否启动");
    } finally {
      setLoading(false);
    }
  }, [date, activePhase, startPolling, stopPolling]);

  useEffect(() => {
    loadData();
    return () => stopPolling();
  }, [loadData, stopPolling]);

  const handleSnapshot = async () => {
    setSnapLoading(true);
    try {
      const res = await triggerLimitUpAnalysisSnapshot(activePhase);
      if (res.success) {
        message.success(`采集完成：封板${res.limit_up_count || 0}只，炸板${res.broken_count || 0}只`);
        loadData();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("采集数据失败");
    } finally {
      setSnapLoading(false);
    }
  };

  const handleGenerate = async () => {
    setGenLoading(true);
    try {
      const res = await triggerLimitUpAnalysisGenerate(date, activePhase);
      if (res.success) {
        const total = res.data?.total ?? 0;
        message.success(`AI分析任务已启动，共 ${total} 只待分析`);
        setTaskStatus({
          active: true,
          total,
          done: 0,
          percent: 0,
          phase: activePhase,
        });
        startPolling(date, activePhase);
      } else if (res.already_running) {
        message.info("已有分析任务在运行中");
        startPolling(date, activePhase);
      } else {
        message.error(res.message || "AI分析生成失败");
        setGenLoading(false);
      }
    } catch {
      message.error("AI分析生成失败");
      setGenLoading(false);
    }
  };

  const filteredItems = useMemo(() => {
    let result = items;
    if (activeBoard !== "all") {
      result = result.filter((item) => item.board === activeBoard);
    }
    if (activeType !== "all") {
      result = result.filter((item) => item.stock_type === activeType);
    }
    return result;
  }, [items, activeBoard, activeType]);

  const limitUpCount = items.filter((i) => i.stock_type === "limit_up").length;
  const brokenCount = items.filter((i) => i.stock_type === "broken").length;
  const analyzedCount = items.filter((i) => i.status === "completed").length;
  const highProbCount = items.filter((i) => i.ai_tomorrow_prob === "high").length;
  const avgConfidence = analyzedCount
    ? (items.filter((i) => i.status === "completed").reduce((s, i) => s + (i.ai_confidence || 0), 0) / analyzedCount * 100).toFixed(0)
    : "--";

  const boardStats = useMemo(() => {
    const stats: Record<string, number> = {};
    for (const item of items) {
      const b = item.board || "其他";
      stats[b] = (stats[b] || 0) + 1;
    }
    return stats;
  }, [items]);

  const tabItems = [
    { key: "all", label: `全部 (${items.length})` },
    ...BOARD_LIST.map((b) => ({
      key: b,
      label: `${b} (${boardStats[b] || 0})`,
    })),
  ].filter((t) => t.key === "all" || (boardStats[t.key] || 0) > 0);

  const probChartOption = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0, "": 0 };
    for (const item of items) {
      const p = item.ai_tomorrow_prob;
      if (p in counts) counts[p as keyof typeof counts]++;
      else counts[""]++;
    }
    return {
      tooltip: { trigger: "item" as const },
      legend: { bottom: 0 },
      series: [{
        type: "pie" as const,
        radius: ["40%", "70%"],
        label: { show: true, formatter: "{b}: {c}只" },
        data: [
          { name: "高概率", value: counts.high, itemStyle: { color: PROB_COLORS.high } },
          { name: "中概率", value: counts.medium, itemStyle: { color: PROB_COLORS.medium } },
          { name: "低概率", value: counts.low, itemStyle: { color: PROB_COLORS.low } },
        ].filter((d) => d.value > 0),
      }],
    };
  }, [items]);

  const boardPieOption = useMemo(() => {
    const boards = BOARD_LIST.filter((b) => boardStats[b]);
    return {
      tooltip: { trigger: "item" as const },
      legend: { bottom: 0 },
      series: [{
        type: "pie" as const,
        radius: ["40%", "70%"],
        label: { show: true, formatter: "{b}: {c}只" },
        data: boards.map((b) => ({ name: b, value: boardStats[b] || 0, itemStyle: { color: BOARD_COLORS[b] } })),
      }],
    };
  }, [boardStats]);

  const columns = [
    {
      title: "代码",
      dataIndex: "code",
      key: "code",
      width: 90,
      render: (v: string, r: LimitUpAnalysisItem) => <StockLink code={v} name={r.name}>{v}</StockLink>,
    },
    { title: "名称", dataIndex: "name", key: "name", width: 90, fixed: "left" as const },
    {
      title: "类型",
      dataIndex: "stock_type",
      key: "stock_type",
      width: 70,
      render: (v: string) => (
        <Tag color={v === "limit_up" ? "red" : "orange"} style={{ margin: 0 }}>
          {v === "limit_up" ? "封板" : "炸板"}
        </Tag>
      ),
    },
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
      width: 80,
      render: (v: number | null) => (v != null ? v.toFixed(2) : "--"),
    },
    {
      title: "涨跌幅",
      dataIndex: "change_pct",
      key: "change_pct",
      width: 90,
      sorter: (a: LimitUpAnalysisItem, b: LimitUpAnalysisItem) => (a.change_pct ?? 0) - (b.change_pct ?? 0),
      render: (v: number | null) => <span style={{ color: POSITIVE_COLOR }}>{fmtPct(v)}</span>,
    },
    {
      title: "连板",
      dataIndex: "limit_up_times",
      key: "limit_up_times",
      width: 60,
      render: (v: number) => (v > 1 ? <span style={{ color: POSITIVE_COLOR, fontWeight: "bold" }}>{v}</span> : v),
    },
    {
      title: "换手率",
      dataIndex: "turnover_rate",
      key: "turnover_rate",
      width: 80,
      render: (v: number | null) => (v != null ? `${v.toFixed(2)}%` : "--"),
    },
    {
      title: "成交额",
      dataIndex: "amount",
      key: "amount",
      width: 90,
      sorter: (a: LimitUpAnalysisItem, b: LimitUpAnalysisItem) => (a.amount ?? 0) - (b.amount ?? 0),
      render: (v: number | null) => fmtAmount(v),
    },
    {
      title: "行业",
      dataIndex: "sector",
      key: "sector",
      width: 90,
    },
    {
      title: "AI涨停原因",
      dataIndex: "ai_reason",
      key: "ai_reason",
      width: 200,
      render: (v: string) => v ? <Tooltip title={v}><span style={{ cursor: "pointer" }}>{v.length > 60 ? v.slice(0, 60) + "..." : v}</span></Tooltip> : <span style={{ color: "#999" }}>待分析</span>,
    },
    {
      title: "AI明日预判",
      dataIndex: "ai_tomorrow_judge",
      key: "ai_tomorrow_judge",
      width: 200,
      render: (v: string) => v ? <Tooltip title={v}><span style={{ cursor: "pointer" }}>{v.length > 60 ? v.slice(0, 60) + "..." : v}</span></Tooltip> : <span style={{ color: "#999" }}>待分析</span>,
    },
    {
      title: "明日概率",
      dataIndex: "ai_tomorrow_prob",
      key: "ai_tomorrow_prob",
      width: 80,
      sorter: (a: LimitUpAnalysisItem, b: LimitUpAnalysisItem) => {
        const order = { high: 3, medium: 2, low: 1 };
        return (order[a.ai_tomorrow_prob as keyof typeof order] || 0) - (order[b.ai_tomorrow_prob as keyof typeof order] || 0);
      },
      render: (v: string) => v ? (
        <Tag color={PROB_COLORS[v] || "default"} style={{ margin: 0 }}>{PROB_LABELS[v] || v}</Tag>
      ) : <span style={{ color: "#999" }}>-</span>,
    },
    {
      title: "置信度",
      dataIndex: "ai_confidence",
      key: "ai_confidence",
      width: 100,
      sorter: (a: LimitUpAnalysisItem, b: LimitUpAnalysisItem) => (a.ai_confidence ?? 0) - (b.ai_confidence ?? 0),
      render: (v: number) => v > 0 ? <Progress percent={Math.round(v * 100)} size="small" strokeColor={v >= 0.7 ? PROB_COLORS.high : v >= 0.4 ? PROB_COLORS.medium : PROB_COLORS.low} /> : <span style={{ color: "#999" }}>-</span>,
    },
    {
      title: "关键因素",
      dataIndex: "ai_key_factors",
      key: "ai_key_factors",
      width: 180,
      render: (v: string | string[]) => {
        const factors = parseKeyFactors(v);
        return factors.length > 0
          ? factors.map((f, i) => <Tag key={i} style={{ marginBottom: 2 }}>{f}</Tag>)
          : <span style={{ color: "#999" }}>-</span>;
      },
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>涨停AI分析</Typography.Title>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => { const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD"); setDate(ds); }}
            size="small"
          />
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => loadData()} size="small">刷新</Button>
          <Button icon={<CameraOutlined />} onClick={handleSnapshot} loading={snapLoading} size="small">采集数据</Button>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={handleGenerate}
            loading={genLoading}
            size="small"
            type="primary"
          >AI分析</Button>
        </div>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      {taskStatus && taskStatus.active && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`AI 分析任务运行中：${taskStatus.done} / ${taskStatus.total} 已分析`}
          description={<Progress percent={taskStatus.percent} size="small" status="active" />}
        />
      )}

      <Tabs
        activeKey={activePhase}
        onChange={(key) => { setActivePhase(key); loadData(undefined, key); }}
        items={[
          { key: "midday", label: "午间 (12:00)" },
          { key: "close", label: "收盘 (15:00)" },
        ]}
        size="small"
        style={{ marginBottom: 16 }}
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="封板数量" value={limitUpCount} valueStyle={{ color: POSITIVE_COLOR }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="炸板数量" value={brokenCount} valueStyle={{ color: "#fa8c16" }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="高概率股" value={highProbCount} valueStyle={{ color: highProbCount > 0 ? POSITIVE_COLOR : undefined }} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="平均置信度" value={avgConfidence} suffix="%" /></Card>
        </Col>
      </Row>

      <Spin spinning={loading && items.length === 0}>
        {items.length > 0 && (
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <Card size="small" title="板块分布" styles={{ body: { padding: 8 } }}>
                <ReactECharts option={boardPieOption} style={{ height: 220 }} notMerge lazyUpdate />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="明日涨停概率分布" styles={{ body: { padding: 8 } }}>
                <ReactECharts option={probChartOption} style={{ height: 220 }} notMerge lazyUpdate />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" title="分析进度" styles={{ body: { padding: 16 } }}>
                <Progress
                  type="circle"
                  percent={taskStatus && taskStatus.total > 0 ? taskStatus.percent : (items.length ? Math.round(analyzedCount / items.length * 100) : 0)}
                  size={120}
                  status={taskStatus && taskStatus.active ? "active" : undefined}
                />
                <div style={{ textAlign: "center", marginTop: 8, color: "#666" }}>
                  {taskStatus && taskStatus.total > 0 ? `${taskStatus.done} / ${taskStatus.total}` : `${analyzedCount} / ${items.length}`} 已分析
                </div>
              </Card>
            </Col>
          </Row>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <Tabs
            activeKey={activeBoard}
            onChange={setActiveBoard}
            items={tabItems}
            size="small"
            style={{ marginBottom: 0 }}
          />
          <Radio.Group
            value={activeType}
            onChange={(e) => setActiveType(e.target.value)}
            size="small"
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="all">全部</Radio.Button>
            <Radio.Button value="limit_up">封板</Radio.Button>
            <Radio.Button value="broken">炸板</Radio.Button>
          </Radio.Group>
        </div>

        <Table
          dataSource={filteredItems}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1800 }}
        />
      </Spin>
    </div>
  );
}
