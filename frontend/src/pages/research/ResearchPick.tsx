import { useState, useEffect, useCallback, useRef } from "react";
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
  Select,
  Space,
  Input,
  Tooltip,
  Modal,
  Tabs,
} from "antd";
import {
  SyncOutlined,
  BulbOutlined,
  LoadingOutlined,
  FileTextOutlined,
  DownloadOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  fetchPicks,
  fetchPickTaskStatus,
  triggerPickGeneration,
  triggerResearchSync,
  fetchReports,
  type ResearchPick,
  type ResearchReport,
  type ResearchPickTaskStatus,
} from "../../api/research";
import StockLink from "../../components/StockLink";

const ADVICE_TAG: Record<string, { color: string; text: string }> = {
  buy: { color: "red", text: "买入" },
  watch: { color: "orange", text: "观察" },
  avoid: { color: "default", text: "回避" },
};

const RATING_COLOR: Record<string, string> = {
  "买入": "red",
  "增持": "orange",
  "中性": "default",
  "减持": "green",
};

export default function ResearchPickPage() {
  const [picks, setPicks] = useState<ResearchPick[]>([]);
  const [picksLoading, setPicksLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [syncLoading, setSyncLoading] = useState(false);
  const [tradeDate, setTradeDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [taskStatus, setTaskStatus] = useState<ResearchPickTaskStatus | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 研报列表
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [reportsTotal, setReportsTotal] = useState(0);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportFilter, setReportFilter] = useState<{
    days: number;
    report_type?: "stock" | "industry";
    rating?: string;
    org?: string;
  }>({ days: 7, report_type: "stock" });

  // 详情 Modal
  const [detailPick, setDetailPick] = useState<ResearchPick | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback((date: string) => {
    stopPolling();
    pollTimerRef.current = setInterval(async () => {
      try {
        const [status, picksRes] = await Promise.all([
          fetchPickTaskStatus(date),
          fetchPicks(date),
        ]);
        setTaskStatus(status);
        setPicks(picksRes.items);
        if (!status.active) {
          stopPolling();
          setGenLoading(false);
          if (status.status === "completed") {
            message.success(`研报选股完成（共 ${picksRes.items.length} 条）`);
          } else if (status.status === "failed") {
            message.error(status.error || "选股失败");
          }
        }
      } catch {
        // 临时错误忽略
      }
    }, 5000);
  }, [stopPolling]);

  const loadPicks = useCallback(async (date?: string) => {
    setPicksLoading(true);
    const td = date || tradeDate;
    try {
      const [picksRes, statusRes] = await Promise.all([
        fetchPicks(td),
        fetchPickTaskStatus(td).catch(() => null),
      ]);
      setPicks(picksRes.items);
      if (picksRes.trade_date && picksRes.trade_date !== td) {
        setTradeDate(picksRes.trade_date);
      }
      if (statusRes) {
        setTaskStatus(statusRes);
        if (statusRes.active) {
          setGenLoading(true);
          startPolling(statusRes.trade_date);
        }
      }
    } catch {
      message.error("获取选股数据失败");
    } finally {
      setPicksLoading(false);
    }
  }, [tradeDate, startPolling]);

  const loadReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const res = await fetchReports({ ...reportFilter, limit: 50 });
      setReports(res.items);
      setReportsTotal(res.total);
    } catch {
      message.error("获取研报列表失败");
    } finally {
      setReportsLoading(false);
    }
  }, [reportFilter]);

  useEffect(() => {
    loadPicks();
    return () => stopPolling();
  }, [loadPicks, stopPolling]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const handleGenerate = async () => {
    setGenLoading(true);
    try {
      const res = await triggerPickGeneration(tradeDate);
      if (res.started) {
        message.success("选股任务已启动，AI 分析约 3-5 分钟");
        startPolling(tradeDate);
      } else if (res.already_running) {
        message.info("任务已在运行，开始轮询进度");
        startPolling(tradeDate);
      } else {
        message.error("启动失败：" + (res as { error?: string }).error);
        setGenLoading(false);
      }
    } catch {
      message.error("启动选股失败");
      setGenLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncLoading(true);
    try {
      const res = await triggerResearchSync(3);
      if (res.status === "ok") {
        message.success(`已抓取 ${res.total} 篇研报（新增 ${res.inserted}）`);
        loadReports();
      } else {
        message.error("抓取失败");
      }
    } catch {
      message.error("抓取研报失败");
    } finally {
      setSyncLoading(false);
    }
  };

  const taskActive = taskStatus?.active === true;

  const pickColumns = [
    {
      title: "代码/名称",
      width: 140,
      render: (_: unknown, r: ResearchPick) => (
        <div>
          <StockLink code={r.code} name={r.code} />
          <div style={{ fontSize: 12, color: "#666" }}>{r.name || "--"}</div>
        </div>
      ),
    },
    {
      title: "AI建议",
      width: 80,
      dataIndex: "ai_advice",
      render: (v: string) => {
        const tag = ADVICE_TAG[v] || { color: "default", text: v || "--" };
        return <Tag color={tag.color}>{tag.text}</Tag>;
      },
      filters: [
        { text: "买入", value: "buy" },
        { text: "观察", value: "watch" },
        { text: "回避", value: "avoid" },
      ],
      onFilter: (val: React.Key | boolean, r: ResearchPick) => r.ai_advice === val,
    },
    {
      title: "评分",
      width: 80,
      dataIndex: "score",
      sorter: (a: ResearchPick, b: ResearchPick) => a.score - b.score,
      defaultSortOrder: "descend" as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: "#cf1322" }}>{v?.toFixed(0) ?? "--"}</span>,
    },
    {
      title: "信心度",
      width: 80,
      dataIndex: "confidence",
      render: (v: number) => v ? `${(v * 100).toFixed(0)}%` : "--",
    },
    {
      title: "共识研报",
      width: 100,
      render: (_: unknown, r: ResearchPick) => (
        <Tooltip title={`买入评级 ${r.buy_rating_count} / 机构 ${r.org_count} 家`}>
          <Space size={4}>
            <Tag color="blue">{r.report_count} 篇</Tag>
            <span style={{ fontSize: 12, color: "#999" }}>买{r.buy_rating_count}/机{r.org_count}</span>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: "目标价/空间",
      width: 120,
      render: (_: unknown, r: ResearchPick) => (
        <div>
          <div>{r.avg_target_price ? `¥${r.avg_target_price.toFixed(2)}` : "--"}</div>
          {r.upside_pct !== null && (
            <div style={{ color: r.upside_pct > 0 ? "#cf1322" : "#3f8600", fontSize: 12 }}>
              {r.upside_pct > 0 ? "+" : ""}{r.upside_pct.toFixed(1)}%
            </div>
          )}
        </div>
      ),
    },
    {
      title: "现价",
      width: 80,
      dataIndex: "current_price",
      render: (v: number | null) => v ? `¥${v.toFixed(2)}` : "--",
    },
    {
      title: "AI 买入区间",
      width: 130,
      render: (_: unknown, r: ResearchPick) => {
        if (!r.ai_buy_low && !r.ai_buy_high) return "--";
        return `${r.ai_buy_low?.toFixed(2) ?? "?"} ~ ${r.ai_buy_high?.toFixed(2) ?? "?"}`;
      },
    },
    {
      title: "止损",
      width: 80,
      dataIndex: "ai_stop_loss",
      render: (v: number | null) => v ? `¥${v.toFixed(2)}` : "--",
    },
    {
      title: "催化剂",
      ellipsis: true,
      render: (_: unknown, r: ResearchPick) => (
        <Tooltip title={r.ai_catalyst}>
          <span style={{ color: "#cf1322" }}>{r.ai_catalyst || "--"}</span>
        </Tooltip>
      ),
    },
    {
      title: "风险点",
      ellipsis: true,
      render: (_: unknown, r: ResearchPick) => (
        <Tooltip title={r.ai_risk}>
          <span style={{ color: "#666" }}>{r.ai_risk || "--"}</span>
        </Tooltip>
      ),
    },
    {
      title: "操作",
      width: 80,
      render: (_: unknown, r: ResearchPick) => (
        <Button type="link" size="small" onClick={() => setDetailPick(r)}>
          详情
        </Button>
      ),
    },
  ];

  const reportColumns = [
    {
      title: "日期",
      width: 100,
      dataIndex: "publish_date",
      render: (v: string) => v || "--",
    },
    {
      title: "类型",
      width: 70,
      dataIndex: "report_type",
      render: (v: string) => (
        <Tag color={v === "stock" ? "blue" : "purple"}>{v === "stock" ? "个股" : "行业"}</Tag>
      ),
    },
    {
      title: "评级",
      width: 70,
      dataIndex: "rating",
      render: (v: string) => v ? <Tag color={RATING_COLOR[v] || "default"}>{v}</Tag> : "--",
    },
    {
      title: "标题",
      ellipsis: true,
      render: (_: unknown, r: ResearchReport) => (
        <Tooltip title={r.summary}>
          <a href={r.url} target="_blank" rel="noreferrer">{r.title}</a>
        </Tooltip>
      ),
    },
    {
      title: "机构",
      width: 120,
      dataIndex: "org",
      render: (v: string) => v || "--",
    },
    {
      title: "分析师",
      width: 100,
      dataIndex: "analyst",
      render: (v: string) => v || "--",
    },
    {
      title: "关联个股",
      width: 120,
      dataIndex: "stock_codes",
      render: (codes: string[]) => (codes && codes.length ? codes.join(", ") : "--"),
    },
    {
      title: "目标价",
      width: 80,
      dataIndex: "target_price",
      render: (v: number | null) => v ? `¥${v.toFixed(2)}` : "--",
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Typography.Title level={4} style={{ margin: 0 }}>研报调研选股</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            自动生成：收盘后 16:00 抓研报 / 16:10 AI 选股（T+1 开盘前就绪）
          </Typography.Text>
        </Space>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <DatePicker
            value={dayjs(tradeDate)}
            onChange={(d) => {
              const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD");
              setTradeDate(ds);
              loadPicks(ds);
            }}
            size="small"
          />
          <Button icon={<SyncOutlined spin={picksLoading} />} onClick={() => loadPicks()} size="small">
            刷新
          </Button>
          <Button
            icon={<DownloadOutlined />}
            loading={syncLoading}
            onClick={handleSync}
            size="small"
          >
            抓取研报
          </Button>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            loading={genLoading}
            onClick={handleGenerate}
            size="small"
          >
            AI 选股
          </Button>
        </div>
      </div>

      {taskActive && (
        <Alert
          type="info"
          showIcon
          icon={<LoadingOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <span>
                正在生成 {taskStatus?.trade_date} 的研报选股
                {taskStatus?.stage ? ` · 当前阶段：${taskStatus.stage}` : ""}
                {taskStatus?.started_at ? ` · 启动于 ${dayjs(taskStatus.started_at).format("HH:mm:ss")}` : ""}
              </span>
              <Progress
                percent={taskStatus?.total ? Math.round((taskStatus.finished / taskStatus.total) * 100) : 30}
                status="active"
                size="small"
                showInfo={false}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                三阶段：规则过滤 → 共识排序 → AI 深度分析（约 3-5 分钟）。可切到其他页面，任务后台继续跑。
              </Typography.Text>
            </Space>
          }
        />
      )}

      <Tabs
        defaultActiveKey="picks"
        items={[
          {
            key: "picks",
            label: `选股结果（${picks.length}）`,
            children: (
              <Spin spinning={picksLoading && picks.length === 0}>
                <Table
                  rowKey="id"
                  dataSource={picks}
                  columns={pickColumns}
                  pagination={{ pageSize: 20, showSizeChanger: false }}
                  size="small"
                  scroll={{ x: 1200 }}
                  locale={{ emptyText: "暂无选股结果，点击右上「AI 选股」生成" }}
                />
              </Spin>
            ),
          },
          {
            key: "reports",
            label: `研报库（${reportsTotal}）`,
            children: (
              <>
                <Space style={{ marginBottom: 12 }} size="small">
                  <Select
                    value={reportFilter.report_type}
                    onChange={(v) => setReportFilter({ ...reportFilter, report_type: v })}
                    size="small"
                    style={{ width: 100 }}
                    options={[
                      { value: "stock", label: "个股研报" },
                      { value: "industry", label: "行业研报" },
                      { value: undefined, label: "全部" },
                    ]}
                  />
                  <Select
                    value={reportFilter.rating}
                    onChange={(v) => setReportFilter({ ...reportFilter, rating: v })}
                    size="small"
                    style={{ width: 100 }}
                    allowClear
                    placeholder="评级"
                    options={[
                      { value: "买入", label: "买入" },
                      { value: "增持", label: "增持" },
                      { value: "中性", label: "中性" },
                      { value: "减持", label: "减持" },
                    ]}
                  />
                  <Select
                    value={reportFilter.days}
                    onChange={(v) => setReportFilter({ ...reportFilter, days: v })}
                    size="small"
                    style={{ width: 110 }}
                    options={[
                      { value: 3, label: "近 3 天" },
                      { value: 7, label: "近 7 天" },
                      { value: 14, label: "近 14 天" },
                      { value: 30, label: "近 30 天" },
                    ]}
                  />
                  <Input
                    placeholder="机构名"
                    value={reportFilter.org || ""}
                    onChange={(e) => setReportFilter({ ...reportFilter, org: e.target.value || undefined })}
                    size="small"
                    style={{ width: 140 }}
                    allowClear
                  />
                  <Button size="small" icon={<SyncOutlined />} onClick={loadReports}>
                    查询
                  </Button>
                </Space>
                <Table
                  rowKey="id"
                  dataSource={reports}
                  columns={reportColumns}
                  loading={reportsLoading}
                  pagination={{ pageSize: 20, showSizeChanger: false }}
                  size="small"
                  scroll={{ x: 1100 }}
                />
              </>
            ),
          },
        ]}
      />

      <Modal
        title={detailPick ? `${detailPick.code} ${detailPick.name}` : ""}
        open={!!detailPick}
        onCancel={() => setDetailPick(null)}
        footer={null}
        width={680}
      >
        {detailPick && (
          <div>
            <Space style={{ marginBottom: 12 }}>
              <Tag color={(ADVICE_TAG[detailPick.ai_advice] || { color: "default" }).color}>
                {ADVICE_TAG[detailPick.ai_advice]?.text || detailPick.ai_advice}
              </Tag>
              <Tag>评分 {detailPick.score?.toFixed(0)}</Tag>
              <Tag>信心 {(detailPick.confidence * 100).toFixed(0)}%</Tag>
              <Tag color="blue">{detailPick.report_count} 篇研报</Tag>
              {detailPick.avg_target_price && (
                <Tag color="orange">目标价 ¥{detailPick.avg_target_price.toFixed(2)}</Tag>
              )}
              {detailPick.upside_pct !== null && (
                <Tag color={detailPick.upside_pct > 0 ? "red" : "green"}>
                  空间 {detailPick.upside_pct > 0 ? "+" : ""}{detailPick.upside_pct.toFixed(1)}%
                </Tag>
              )}
            </Space>
            <Typography.Paragraph>
              <Typography.Text strong>AI 综合分析：</Typography.Text>
              <br />
              {detailPick.ai_analysis || "（无）"}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <Typography.Text strong style={{ color: "#cf1322" }}>核心催化剂：</Typography.Text>
              <br />
              {detailPick.ai_catalyst || "（无）"}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <Typography.Text strong style={{ color: "#999" }}>主要风险：</Typography.Text>
              <br />
              {detailPick.ai_risk || "（无）"}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <Typography.Text strong>操作建议：</Typography.Text>
              <br />
              现价 ¥{detailPick.current_price?.toFixed(2) ?? "--"} |
              买入区间 {detailPick.ai_buy_low?.toFixed(2) ?? "--"} ~ {detailPick.ai_buy_high?.toFixed(2) ?? "--"} |
              止损 ¥{detailPick.ai_stop_loss?.toFixed(2) ?? "--"}
            </Typography.Paragraph>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              <FileTextOutlined /> 模型：{detailPick.model_used} · 生成于 {detailPick.trade_date}
            </Typography.Text>
          </div>
        )}
      </Modal>
    </div>
  );
}
