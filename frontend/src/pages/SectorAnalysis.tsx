import { useState, useEffect, useCallback, useRef } from "react";
import {
  Typography, Card, Table, Tag, Statistic, Row, Col, Button, Spin, Alert, DatePicker, Space, message, Tabs, Progress,
} from "antd";
import {
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined, ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  fetchLatestSectorAnalysis,
  fetchSectorAnalysisHistory,
  fetchSectorAnalysisTaskStatus,
  triggerSectorAnalysis,
  triggerSectorReview,
} from "../api/sectorAnalysis";
import { fetchActiveStrategy } from "../api/strategy";
import type { StrategyItem } from "../api/strategy";
import type {
  SectorAnalysisItem, SectorAnalysisTaskStatus, SectorPredictionItem, SectorPredictionSummary, ScoredNewsItem,
} from "../types";

function DirectionTag({ direction }: { direction: string }) {
  if (direction === "up") return <Tag color="red" icon={<ArrowUpOutlined />}>看涨</Tag>;
  if (direction === "down") return <Tag color="green" icon={<ArrowDownOutlined />}>看跌</Tag>;
  return <Tag icon={<MinusOutlined />}>看平</Tag>;
}

function RiskTag({ level }: { level: string }) {
  const color = level === "high" ? "red" : level === "medium" ? "orange" : "green";
  return <Tag color={color}>{level === "high" ? "高" : level === "medium" ? "中" : "低"}</Tag>;
}

function StatusTag({ status }: { status: string }) {
  if (status === "reviewed") return <Tag color="blue">已复盘</Tag>;
  if (status === "analyzed") return <Tag color="green">已分析</Tag>;
  return <Tag color="default">待分析</Tag>;
}

const SECTOR_LABELS: Record<string, string> = { industry: "行业板块", concept: "概念板块" };

/* ────────────────────────── Sector Analysis Tab ────────────────────────── */

function SectorAnalysisTab({ sectorType }: { sectorType: string }) {
  const label = SECTOR_LABELS[sectorType] || sectorType;
  const [latest, setLatest] = useState<SectorAnalysisItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<SectorAnalysisItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [taskStatus, setTaskStatus] = useState<SectorAnalysisTaskStatus | null>(null);
  const [taskDate, setTaskDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [page, setPage] = useState(1);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pageSize = 10;

  const loadLatest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLatestSectorAnalysis(sectorType);
      setLatest(res);
    } catch {
      setError(`获取${label}分析数据失败`);
    } finally {
      setLoading(false);
    }
  }, [sectorType, label]);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchSectorAnalysisHistory(pageSize, (page - 1) * pageSize, sectorType);
      setHistoryItems(res.items);
      setHistoryTotal(res.total);
    } catch {
      // silently ignore
    }
  }, [page, sectorType]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollTask = useCallback(async (tradeDate: string) => {
    try {
      const status = await fetchSectorAnalysisTaskStatus(tradeDate, sectorType);
      setTaskStatus(status);
      if (!status.active) {
        stopPolling();
        setGenerating(false);
        if (status.status === "completed") {
          message.success(`${label}分析完成`);
          loadLatest();
          loadHistory();
        } else if (status.status === "failed") {
          message.error(status.error || `${label}分析失败`);
        }
      }
    } catch {
      // keep polling transient failures
    }
  }, [sectorType, label, loadLatest, loadHistory, stopPolling]);

  const startPolling = useCallback((tradeDate: string) => {
    stopPolling();
    pollTimerRef.current = setInterval(() => pollTask(tradeDate), 5000);
  }, [pollTask, stopPolling]);

  useEffect(() => { loadLatest(); }, [loadLatest]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => {
    fetchSectorAnalysisTaskStatus(taskDate, sectorType).then((status) => {
      setTaskStatus(status);
      if (status.active) {
        setGenerating(true);
        startPolling(taskDate);
      }
    }).catch(() => {});
    return () => stopPolling();
  }, [taskDate, sectorType, startPolling, stopPolling]);

  const handleGenerate = async (date?: string) => {
    const tradeDate = date || dayjs().format("YYYY-MM-DD");
    setTaskDate(tradeDate);
    setGenerating(true);
    try {
      const res = await triggerSectorAnalysis(tradeDate, sectorType);
      if (res.success) {
        message.success(res.message);
        const status = await fetchSectorAnalysisTaskStatus(tradeDate, sectorType);
        setTaskStatus(status);
        startPolling(tradeDate);
      } else {
        message.error(res.message);
        setGenerating(false);
      }
    } catch {
      message.error("生成失败，请检查后端服务");
      setGenerating(false);
    }
  };

  const summary = latest?.prediction_summary as SectorPredictionSummary | undefined;

  const historyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    {
      title: "预测方向", key: "dir",
      render: (_: unknown, r: SectorAnalysisItem) => {
        const ps = r.prediction_summary as SectorPredictionSummary | undefined;
        return ps?.overall_rotation ? <span>{ps.overall_rotation.slice(0, 10)}</span> : "-";
      },
    },
    {
      title: "置信度", key: "conf",
      render: (_: unknown, r: SectorAnalysisItem) => {
        const ps = r.prediction_summary as SectorPredictionSummary | undefined;
        return ps?.confidence != null ? `${(ps.confidence * 100).toFixed(0)}%` : "-";
      },
    },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <StatusTag status={s} /> },
    { title: "模型", dataIndex: "model_used", key: "model" },
  ];

  const predictionColumns = [
    { title: "板块", dataIndex: "name", key: "name" },
    {
      title: "方向", dataIndex: "direction", key: "direction", width: 80,
      render: (d: string) => <DirectionTag direction={d} />,
    },
    {
      title: "置信度", dataIndex: "confidence", key: "confidence", width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0.7 ? "#cf1322" : v >= 0.4 ? "#fa8c16" : "#999" }}>
          {(v * 100).toFixed(0)}%
        </span>
      ),
    },
    {
      title: "热度", dataIndex: "heat", key: "heat", width: 80,
      render: (v: number) => <Progress percent={v * 10} size="small" strokeColor={v >= 7 ? "#cf1322" : v >= 5 ? "#fa8c16" : "#52c41a"} />,
    },
    {
      title: "风险", dataIndex: "risk_level", key: "risk", width: 80,
      render: (l: string) => <RiskTag level={l} />,
    },
    {
      title: "驱动因素", dataIndex: "key_drivers", key: "drivers",
      render: (drivers: string[]) => drivers?.map((d, i) => <Tag key={i} style={{ marginBottom: 2 }}>{d}</Tag>),
    },
  ];

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <DatePicker
            onChange={(d) => { if (d) handleGenerate(d.format("YYYY-MM-DD")); }}
            placeholder="选择日期手动生成"
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={() => handleGenerate()}>
            生成{label}分析
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}
      {taskStatus?.active && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`${label}分析任务运行中`}
          description={
            <div>
              <div style={{ marginBottom: 8 }}>当前阶段：{taskStatus.stage || "处理中"}</div>
              <Progress percent={taskStatus.stage ? 50 : 10} status="active" showInfo={false} />
            </div>
          }
        />
      )}
      {taskStatus?.status === "failed" && taskStatus.error && (
        <Alert message={`${label}分析失败`} description={taskStatus.error} type="error" showIcon style={{ marginBottom: 16 }} />
      )}

      <Spin spinning={loading}>
        {latest && (
          <>
            <Card title={`${latest.trade_date} ${label}AI分析`} style={{ marginBottom: 16 }}>
              <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8 }}>
                {latest.analysis_text || "暂无分析内容"}
              </Typography.Paragraph>
            </Card>

            {latest.scored_news && latest.scored_news.length > 0 && (
              <Card title={`${label}相关新闻`} style={{ marginBottom: 16 }}>
                <Table<ScoredNewsItem>
                  size="small"
                  pagination={false}
                  dataSource={latest.scored_news}
                  rowKey={(_, i) => String(i)}
                  columns={[
                    {
                      title: "排名", key: "rank", width: 50,
                      render: (_: unknown, __: unknown, i: number) => (
                        <span style={{ fontWeight: i < 3 ? "bold" : "normal", color: i < 3 ? "#cf1322" : undefined }}>{i + 1}</span>
                      ),
                    },
                    {
                      title: "影响力", dataIndex: "impact_score", key: "score", width: 90,
                      render: (v: number) => {
                        const color = v >= 8 ? "#cf1322" : v >= 6 ? "#fa8c16" : v >= 4 ? "#faad14" : "#d9d9d9";
                        return <span style={{ color, fontWeight: "bold" }}>{v}/10</span>;
                      },
                      sorter: (a: ScoredNewsItem, b: ScoredNewsItem) => a.impact_score - b.impact_score,
                      defaultSortOrder: "descend",
                    },
                    {
                      title: "分类", dataIndex: "impact_category", key: "cat", width: 90,
                      render: (v: string) => {
                        const catColors: Record<string, string> = {
                          "政策变动": "red", "宏观经济": "purple", "外围市场": "blue",
                          "行业动态": "cyan", "资金面": "gold", "公司事件": "geekblue",
                        };
                        return <Tag color={catColors[v] || "default"}>{v}</Tag>;
                      },
                    },
                    {
                      title: "来源", dataIndex: "source", key: "source", width: 90,
                      render: (v: string) => {
                        const labels: Record<string, string> = {
                          eastmoney: "东方财富", eastmoney_global: "7x24全球",
                          cls: "财联社", cls_red: "财联社·加红", cls_announcement: "财联社·公司",
                          cls_watch: "财联社·看盘", cls_hk_us: "财联社·港美股",
                          cls_fund: "财联社·基金", cls_remind: "财联社·提醒",
                          tonghuashun: "同花顺", sina: "新浪财经", wallstreetcn: "华尔街见闻",
                          yicai: "第一财经", futu: "富途", xueqiu: "雪球", jrj: "金融界",
                        };
                        return <Tag>{labels[v] || v}</Tag>;
                      },
                    },
                    {
                      title: "发布时间", dataIndex: "publish_time", key: "time", width: 140,
                      render: (v: string) => v ? dayjs(v).format("MM-DD HH:mm") : "-",
                    },
                    {
                      title: "标题", dataIndex: "title", key: "title",
                      render: (v: string, r: ScoredNewsItem) =>
                        r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer">{v}</a> : v,
                    },
                  ]}
                />
              </Card>
            )}

            {summary && (
              <Card title={`次日${label}预测`} style={{ marginBottom: 16 }}>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={6}>
                    <Statistic title="预测板块数" value={summary.predicted_active_sectors?.length ?? 0} suffix="个" />
                  </Col>
                  <Col span={6}>
                    <Statistic title="整体置信度" value={summary.confidence != null ? (summary.confidence * 100).toFixed(0) : "-"} suffix="%" />
                  </Col>
                  <Col span={6}>
                    <Statistic title="风险等级" valueRender={() => <RiskTag level={summary.risk_level || "medium"} />} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="关键因素" value={summary.key_factors?.length ?? 0} suffix="项" />
                  </Col>
                </Row>

                {summary.overall_rotation && (
                  <div style={{ marginBottom: 12 }}>
                    <Typography.Text strong>轮动方向：</Typography.Text>
                    <Typography.Text>{summary.overall_rotation}</Typography.Text>
                  </div>
                )}

                {summary.key_factors && summary.key_factors.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Typography.Text strong>关键因素：</Typography.Text>
                    <div style={{ marginTop: 4 }}>
                      {summary.key_factors.map((f, i) => (<Tag key={i} style={{ marginBottom: 4 }}>{f}</Tag>))}
                    </div>
                  </div>
                )}

                {summary.predicted_active_sectors && summary.predicted_active_sectors.length > 0 && (
                  <Table<SectorPredictionItem>
                    size="small"
                    pagination={false}
                    dataSource={summary.predicted_active_sectors}
                    rowKey="name"
                    columns={predictionColumns}
                  />
                )}
              </Card>
            )}

            {latest.status === "reviewed" && latest.review_text && (
              <Card title={`${label}预测复盘`} style={{ marginBottom: 16 }}>
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8 }}>
                  {latest.review_text}
                </Typography.Paragraph>
                {latest.actual_data && summary?.predicted_active_sectors && (
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={summary.predicted_active_sectors.map((p) => {
                      const actual = latest.actual_data as { top_gainers?: { name: string; change_pct: number | null }[] };
                      const actualItem = actual.top_gainers?.find((a) => a.name === p.name);
                      return { key: p.name, ...p, actual_change_pct: actualItem?.change_pct };
                    })}
                    columns={[
                      { title: "板块", dataIndex: "name", key: "name" },
                      {
                        title: "预测方向", dataIndex: "direction", key: "pred_dir", width: 80,
                        render: (d: string) => <DirectionTag direction={d} />,
                      },
                      {
                        title: "实际涨跌幅", dataIndex: "actual_change_pct", key: "actual", width: 100,
                        render: (v: number | null | undefined) => {
                          if (v == null) return "-";
                          const color = v > 0 ? "#cf1322" : v < 0 ? "#3f8600" : undefined;
                          return <span style={{ color }}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
                        },
                      },
                      {
                        title: "结果", key: "result", width: 60,
                        render: (_: unknown, r: SectorPredictionItem & { actual_change_pct?: number | null }) => {
                          if (r.actual_change_pct == null) return "-";
                          const predDir = r.direction;
                          const actualDir = r.actual_change_pct > 0.1 ? "up" : r.actual_change_pct < -0.1 ? "down" : "flat";
                          if (predDir === actualDir) return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
                          return <CloseCircleOutlined style={{ color: "#ff4d4f" }} />;
                        },
                      },
                    ]}
                    style={{ marginTop: 12 }}
                  />
                )}
              </Card>
            )}
          </>
        )}

        {!latest && !loading && (
          <Card><Typography.Text type="secondary">暂无{label}分析数据，点击"生成{label}分析"开始</Typography.Text></Card>
        )}
      </Spin>

      <Card title={`历史${label}分析`} style={{ marginTop: 16 }}>
        <Table
          size="small"
          dataSource={historyItems}
          columns={historyColumns}
          rowKey="id"
          pagination={{ current: page, pageSize, total: historyTotal, onChange: setPage, showTotal: (t) => `共 ${t} 条` }}
          onRow={(r) => ({ onClick: () => setLatest(r), style: { cursor: "pointer" } })}
        />
      </Card>
    </>
  );
}

/* ────────────────────────── Review Tab ────────────────────────── */

function SectorReviewTab() {
  const [generating, setGenerating] = useState(false);
  const [industryLatest, setIndustryLatest] = useState<SectorAnalysisItem | null>(null);
  const [conceptLatest, setConceptLatest] = useState<SectorAnalysisItem | null>(null);
  const [historyItems, setHistoryItems] = useState<SectorAnalysisItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadReviewed = useCallback(async () => {
    try {
      const [ind, con] = await Promise.all([
        fetchLatestSectorAnalysis("industry"),
        fetchLatestSectorAnalysis("concept"),
      ]);
      setIndustryLatest(ind?.status === "reviewed" ? ind : null);
      setConceptLatest(con?.status === "reviewed" ? con : null);
    } catch {
      // ignore
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchSectorAnalysisHistory(pageSize, (page - 1) * pageSize);
      const reviewed = res.items.filter((i) => i.status === "reviewed");
      setHistoryItems(reviewed);
      setHistoryTotal(reviewed.length);
    } catch {
      // ignore
    }
  }, [page]);

  useEffect(() => { loadReviewed(); }, [loadReviewed]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const handleReview = async (date?: string) => {
    setGenerating(true);
    try {
      const res = await triggerSectorReview(date);
      if (res.success) {
        message.success(res.message);
        loadReviewed();
        loadHistory();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成复盘失败，请检查后端服务");
    } finally {
      setGenerating(false);
    }
  };

  const renderReviewSection = (item: SectorAnalysisItem | null, label: string) => {
    if (!item) return <Card style={{ marginBottom: 16 }}><Typography.Text type="secondary">暂无{label}复盘数据</Typography.Text></Card>;
    const summary = item.prediction_summary as SectorPredictionSummary | undefined;
    return (
      <>
        <Card title={`${item.trade_date} ${label}复盘`} style={{ marginBottom: 16 }}>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8 }}>
            {item.review_text || "暂无复盘内容"}
          </Typography.Paragraph>
        </Card>
        {summary?.predicted_active_sectors && item.actual_data && (
          <Card title={`${label}预测 vs 实际`} style={{ marginBottom: 16 }}>
            <Table
              size="small"
              pagination={false}
              dataSource={summary.predicted_active_sectors.map((p) => {
                const actual = item.actual_data as { top_gainers?: { name: string; change_pct: number | null }[] };
                const actualItem = actual.top_gainers?.find((a) => a.name === p.name);
                return { key: p.name, ...p, actual_change_pct: actualItem?.change_pct };
              })}
              columns={[
                { title: "板块", dataIndex: "name", key: "name" },
                {
                  title: "预测方向", dataIndex: "direction", key: "pred_dir", width: 80,
                  render: (d: string) => <DirectionTag direction={d} />,
                },
                {
                  title: "预测置信度", dataIndex: "confidence", key: "conf", width: 100,
                  render: (v: number) => `${(v * 100).toFixed(0)}%`,
                },
                {
                  title: "实际涨跌幅", dataIndex: "actual_change_pct", key: "actual", width: 100,
                  render: (v: number | null | undefined) => {
                    if (v == null) return "-";
                    const color = v > 0 ? "#cf1322" : v < 0 ? "#3f8600" : undefined;
                    return <span style={{ color }}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
                  },
                },
                {
                  title: "结果", key: "result", width: 60,
                  render: (_: unknown, r: SectorPredictionItem & { actual_change_pct?: number | null }) => {
                    if (r.actual_change_pct == null) return "-";
                    const predDir = r.direction;
                    const actualDir = r.actual_change_pct > 0.1 ? "up" : r.actual_change_pct < -0.1 ? "down" : "flat";
                    if (predDir === actualDir) return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
                    return <CloseCircleOutlined style={{ color: "#ff4d4f" }} />;
                  },
                },
              ]}
            />
          </Card>
        )}
      </>
    );
  };

  const historyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    { title: "类型", dataIndex: "sector_type", key: "sector_type", render: (s: string) => SECTOR_LABELS[s] || s },
    { title: "模型", dataIndex: "model_used", key: "model" },
    { title: "复盘时间", dataIndex: "updated_at", key: "updated_at" },
  ];

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <DatePicker
            onChange={(d) => { if (d) handleReview(d.format("YYYY-MM-DD")); }}
            placeholder="选择日期生成复盘"
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={() => handleReview()}>
            生成今日复盘
          </Button>
        </Space>
      </div>

      {renderReviewSection(industryLatest, "行业板块")}
      {renderReviewSection(conceptLatest, "概念板块")}

      <Card title="历史复盘记录" style={{ marginTop: 16 }}>
        <Table
          size="small"
          dataSource={historyItems}
          columns={historyColumns}
          rowKey="id"
          pagination={{ current: page, pageSize, total: historyTotal, onChange: setPage, showTotal: (t) => `共 ${t} 条` }}
          onRow={(r) => ({ onClick: () => {
            if (r.sector_type === "industry") setIndustryLatest(r);
            else if (r.sector_type === "concept") setConceptLatest(r);
          }, style: { cursor: "pointer" } })}
        />
      </Card>
    </>
  );
}

/* ────────────────────────── Main Page ────────────────────────── */

export default function SectorAnalysis() {
  const [activeStrategy, setActiveStrategy] = useState<StrategyItem | null>(null);

  useEffect(() => {
    fetchActiveStrategy("sector_analysis").then(setActiveStrategy).catch(() => {});
  }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>板块AI分析</Typography.Title>
        {activeStrategy && (
          <Space>
            <Tag color="green">当前策略：{activeStrategy.name}</Tag>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              自动复盘：工作日 15:30；自动分析：工作日 15:45 / 周日 21:00
            </Typography.Text>
          </Space>
        )}
      </div>
      <Tabs
        defaultActiveKey="industry"
        items={[
          { key: "industry", label: "行业板块分析", children: <SectorAnalysisTab sectorType="industry" /> },
          { key: "concept", label: "概念板块分析", children: <SectorAnalysisTab sectorType="concept" /> },
          { key: "review", label: "预测复盘", children: <SectorReviewTab /> },
        ]}
      />
    </div>
  );
}
