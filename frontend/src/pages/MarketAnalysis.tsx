import { useState, useEffect, useCallback } from "react";
import {
  Typography, Card, Table, Tag, Statistic, Row, Col, Button, Spin, Alert, DatePicker, Space, message, Descriptions, Tabs,
} from "antd";
import {
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined, ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { fetchLatestAnalysis, fetchAnalysisHistory, triggerAnalysis } from "../api/marketAnalysis";
import { fetchLatestReport, fetchReportHistory, triggerReport } from "../api/aiDailyReport";
import type { MarketAnalysisItem, AiDailyReportItem, ScoredNewsItem } from "../types";

const INDEX_NAMES: Record<string, string> = {
  sh000001: "上证指数", sz399001: "深证成指", sz399006: "创业板指",
  sh000688: "科创50", sh000300: "沪深300", sh000016: "上证50",
  sh000905: "中证500", sh000852: "中证1000",
};

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

/* ────────────────────────── Tab 1: 每日分析和预测 ────────────────────────── */

function DailyAnalysisTab() {
  const [latest, setLatest] = useState<MarketAnalysisItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<MarketAnalysisItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadLatest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLatestAnalysis();
      setLatest(res);
    } catch {
      setError("获取分析数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchAnalysisHistory(pageSize, (page - 1) * pageSize);
      setHistoryItems(res.items);
      setHistoryTotal(res.total);
    } catch {
      // silently ignore
    }
  }, [page]);

  useEffect(() => { loadLatest(); }, [loadLatest]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const handleGenerate = async (date?: string) => {
    setGenerating(true);
    try {
      const res = await triggerAnalysis(date);
      if (res.success) {
        message.success(res.message);
        setLatest(res.data);
        loadHistory();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成失败，请检查后端服务");
    } finally {
      setGenerating(false);
    }
  };

  const summary = latest?.prediction_summary as MarketAnalysisItem["prediction_summary"] | undefined;
  const actualData = latest?.actual_data as MarketAnalysisItem["actual_data"] | undefined;

  const compareColumns = [
    { title: "指数", dataIndex: "name", key: "name" },
    {
      title: "预测方向", key: "pred_dir",
      render: (_: unknown, r: { code: string }) => {
        const idx = summary?.indices?.[r.code];
        if (!idx) return "-";
        const pct = idx.predicted_change_pct ?? 0;
        return pct > 0.1 ? <span style={{ color: "#cf1322" }}>涨</span> : pct < -0.1 ? <span style={{ color: "#3f8600" }}>跌</span> : <span>平</span>;
      },
    },
    {
      title: "预测涨跌幅", key: "pred_pct",
      render: (_: unknown, r: { code: string }) => {
        const pct = summary?.indices?.[r.code]?.predicted_change_pct;
        if (pct == null) return "-";
        const color = pct > 0 ? "#cf1322" : pct < 0 ? "#3f8600" : undefined;
        return <span style={{ color }}>{pct > 0 ? "+" : ""}{pct.toFixed(2)}%</span>;
      },
    },
    {
      title: "实际涨跌幅", key: "actual_pct",
      render: (_: unknown, r: { code: string }) => {
        const pct = actualData?.indices?.[r.code]?.change_pct;
        if (pct == null) return "-";
        const color = pct > 0 ? "#cf1322" : pct < 0 ? "#3f8600" : undefined;
        return <span style={{ color }}>{pct > 0 ? "+" : ""}{pct.toFixed(2)}%</span>;
      },
    },
    {
      title: "结果", key: "result",
      render: (_: unknown, r: { code: string }) => {
        const predPct = summary?.indices?.[r.code]?.predicted_change_pct ?? 0;
        const actualPct = actualData?.indices?.[r.code]?.change_pct ?? 0;
        const predDir = predPct > 0.1 ? "up" : predPct < -0.1 ? "down" : "flat";
        const actualDir = actualPct > 0.1 ? "up" : actualPct < -0.1 ? "down" : "flat";
        if (predDir === actualDir) return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
        return <CloseCircleOutlined style={{ color: "#ff4d4f" }} />;
      },
    },
  ];

  const compareData = Object.keys(INDEX_NAMES).map((code) => ({ code, name: INDEX_NAMES[code], key: code }));

  const historyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    {
      title: "预测方向", key: "dir",
      render: (_: unknown, r: MarketAnalysisItem) => {
        const dir = (r.prediction_summary as { overall_direction?: string })?.overall_direction;
        return dir ? <DirectionTag direction={dir} /> : "-";
      },
    },
    {
      title: "置信度", key: "conf",
      render: (_: unknown, r: MarketAnalysisItem) => {
        const c = (r.prediction_summary as { confidence?: number })?.confidence;
        return c != null ? `${(c * 100).toFixed(0)}%` : "-";
      },
    },
    {
      title: "风险", key: "risk",
      render: (_: unknown, r: MarketAnalysisItem) => {
        const lvl = (r.prediction_summary as { risk_level?: string })?.risk_level;
        return lvl ? <RiskTag level={lvl} /> : "-";
      },
    },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => <StatusTag status={s} /> },
    { title: "模型", dataIndex: "model_used", key: "model" },
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
            生成今日分析
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Spin spinning={loading}>
        {latest && (
          <>
            <Card title={`📊 ${latest.trade_date} 大盘分析`} style={{ marginBottom: 16 }}>
              <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>
                {latest.analysis_text || "暂无分析内容"}
              </Typography.Paragraph>
            </Card>

            {latest.scored_news && latest.scored_news.length > 0 && (
              <Card title="📰 资讯影响力排行" style={{ marginBottom: 16 }}>
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
                      title: "影响力", dataIndex: "impact_score", key: "score", width: 100,
                      render: (v: number) => {
                        const color = v >= 8 ? "#cf1322" : v >= 6 ? "#fa8c16" : v >= 4 ? "#faad14" : "#d9d9d9";
                        return <span style={{ color, fontWeight: "bold" }}>{v}/10</span>;
                      },
                      sorter: (a: ScoredNewsItem, b: ScoredNewsItem) => a.impact_score - b.impact_score,
                      defaultSortOrder: "descend",
                    },
                    {
                      title: "分类", dataIndex: "impact_category", key: "cat", width: 100,
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
                    },
                    {
                      title: "标题", dataIndex: "title", key: "title",
                    },
                  ]}
                />
              </Card>
            )}

            {summary && (
              <Card title="🔮 次日预测" style={{ marginBottom: 16 }}>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={6}><Statistic title="预测方向" valueRender={() => <DirectionTag direction={summary.overall_direction} />} /></Col>
                  <Col span={6}><Statistic title="置信度" value={(summary.confidence * 100).toFixed(0)} suffix="%" /></Col>
                  <Col span={6}><Statistic title="风险等级" valueRender={() => <RiskTag level={summary.risk_level} />} /></Col>
                  <Col span={6}><Statistic title="关键因素" value={summary.key_factors?.length ?? 0} suffix="项" /></Col>
                </Row>

                {summary.key_factors && summary.key_factors.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Typography.Text strong>关键因素：</Typography.Text>
                    <div style={{ marginTop: 4 }}>
                      {summary.key_factors.map((f, i) => (<Tag key={i} style={{ marginBottom: 4 }}>{f}</Tag>))}
                    </div>
                  </div>
                )}

                {summary.prediction_text && (
                  <Typography.Paragraph style={{ whiteSpace: "pre-wrap", color: "#666", fontSize: 13 }}>
                    {latest.prediction_text}
                  </Typography.Paragraph>
                )}

                {summary.indices && Object.keys(summary.indices).length > 0 && (
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={Object.entries(summary.indices).map(([code, v]) => ({ key: code, code, name: INDEX_NAMES[code] || code, ...v }))}
                    columns={[
                      { title: "指数", dataIndex: "name", key: "name" },
                      {
                        title: "预测涨跌幅", dataIndex: "predicted_change_pct", key: "pct",
                        render: (v: number | null) => {
                          if (v == null) return "-";
                          const color = v > 0 ? "#cf1322" : v < 0 ? "#3f8600" : undefined;
                          return <span style={{ color }}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
                        },
                      },
                      { title: "支撑位", dataIndex: "support", key: "support", render: (v: number | null) => v?.toFixed(2) ?? "-" },
                      { title: "阻力位", dataIndex: "resistance", key: "resistance", render: (v: number | null) => v?.toFixed(2) ?? "-" },
                    ]}
                  />
                )}
              </Card>
            )}

            {latest.status === "reviewed" && latest.review_text && (
              <Card title="📝 预测复盘" style={{ marginBottom: 16 }}>
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>
                  {latest.review_text}
                </Typography.Paragraph>
                {actualData?.indices && summary?.indices && (
                  <Table size="small" pagination={false} dataSource={compareData} columns={compareColumns} style={{ marginTop: 12 }} />
                )}
              </Card>
            )}
          </>
        )}

        {!latest && !loading && (
          <Card><Typography.Text type="secondary">暂无分析数据，点击"生成今日分析"开始</Typography.Text></Card>
        )}
      </Spin>

      <Card title="历史分析" style={{ marginTop: 16 }}>
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

/* ────────────────────────── Tab 2: 收盘分析 ────────────────────────── */

function ClosingReportTab() {
  const [latest, setLatest] = useState<AiDailyReportItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [historyItems, setHistoryItems] = useState<AiDailyReportItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const loadLatest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLatestReport();
      setLatest(res);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchReportHistory(pageSize, (page - 1) * pageSize);
      setHistoryItems(res.items);
      setHistoryTotal(res.total);
    } catch {
      // ignore
    }
  }, [page]);

  useEffect(() => { loadLatest(); }, [loadLatest]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const handleGenerate = async (date?: string) => {
    setGenerating(true);
    try {
      const res = await triggerReport(date);
      if (res.success) {
        message.success(res.message);
        setLatest(res.data);
        loadHistory();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成失败，请检查后端服务");
    } finally {
      setGenerating(false);
    }
  };

  const historyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => s === "completed" ? <Tag color="green">已完成</Tag> : <Tag color="default">{s}</Tag> },
    { title: "模型", dataIndex: "model_used", key: "model" },
    { title: "生成时间", dataIndex: "created_at", key: "created_at" },
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
            生成收盘分析
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {latest && (
          <Card title={`📋 ${latest.trade_date} AI 收盘分析报告`} style={{ marginBottom: 16 }}>
            <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8 }}>
              {latest.report_text || "暂无报告内容"}
            </Typography.Paragraph>
          </Card>
        )}
        {!latest && !loading && (
          <Card><Typography.Text type="secondary">暂无收盘分析报告，点击"生成收盘分析"开始</Typography.Text></Card>
        )}
      </Spin>

      <Card title="历史报告" style={{ marginTop: 16 }}>
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

/* ────────────────────────── Main Page ────────────────────────── */

export default function MarketAnalysis() {
  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>AI 每日分析</Typography.Title>
      <Tabs
        defaultActiveKey="daily"
        items={[
          { key: "daily", label: "每日分析和预测", children: <DailyAnalysisTab /> },
          { key: "closing", label: "收盘分析", children: <ClosingReportTab /> },
        ]}
      />
    </div>
  );
}
