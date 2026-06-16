import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Input,
  Progress,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { BulbOutlined, SyncOutlined, LoadingOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import StockLink from "../../components/StockLink";
import {
  fetchLatestStockAnalysis,
  fetchStockAnalysisHistory,
  fetchStockAnalysisTaskStatus,
  triggerStockAnalysis,
  type StockAnalysisTaskStatus,
} from "../../api/stockAnalysis";
import type { StockAnalysisItem } from "../../types";

const PAGE_SIZE = 20;
const POSITIVE_COLOR = "#cf1322";
const NEGATIVE_COLOR = "#3f8600";

const directionLabels: Record<string, string> = {
  up: "看涨",
  down: "看跌",
  flat: "震荡",
};

const actionLabels: Record<string, string> = {
  watch: "观察",
  buy: "买入",
  hold: "持有",
  avoid: "规避",
};

const riskColors: Record<string, string> = {
  low: "green",
  medium: "orange",
  high: "red",
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function fmtNumber(value: unknown, digits = 2): string {
  const num = asNumber(value);
  return num == null ? "--" : num.toFixed(digits);
}

function fmtPct(value: unknown): string {
  const num = asNumber(value);
  if (num == null) return "--";
  return `${num > 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function fmtAmount(value: unknown): string {
  const num = asNumber(value);
  if (num == null) return "--";
  if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)}亿`;
  if (Math.abs(num) >= 10000) return `${(num / 10000).toFixed(2)}万`;
  return num.toFixed(2);
}

function valueColor(value: unknown): string | undefined {
  const num = asNumber(value);
  if (num == null || num === 0) return undefined;
  return num > 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;
}

function summaryValue(record: StockAnalysisItem, key: string): unknown {
  return record.prediction_summary?.[key as keyof typeof record.prediction_summary];
}

function keyFactors(record: StockAnalysisItem): string[] {
  const factors = summaryValue(record, "key_factors");
  return Array.isArray(factors) ? factors.filter((item): item is string => typeof item === "string") : [];
}

function renderDirection(value?: string) {
  if (!value) return <Tag>--</Tag>;
  const color = value === "up" ? "red" : value === "down" ? "green" : "blue";
  return <Tag color={color}>{directionLabels[value] || value}</Tag>;
}

function renderRisk(value?: string) {
  if (!value) return <Tag>--</Tag>;
  return <Tag color={riskColors[value] || "default"}>{value}</Tag>;
}

function AnalysisCard({ record }: { record: StockAnalysisItem | null }) {
  if (!record) {
    return (
      <Card>
        <Empty description="暂无个股分析记录，请输入股票代码后生成分析" />
      </Card>
    );
  }

  const confidence = asNumber(summaryValue(record, "confidence"));
  const direction = summaryValue(record, "direction") as string | undefined;
  const action = summaryValue(record, "suggested_action") as string | undefined;
  const risk = summaryValue(record, "risk_level") as string | undefined;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title={
          <Space>
            <StockLink code={record.code} name={record.name}>{record.code}</StockLink>
            <Typography.Text strong>{record.name}</Typography.Text>
            <Tag>{record.board || "--"}</Tag>
            <Tag color={record.status === "completed" ? "green" : record.status === "failed" ? "red" : "orange"}>
              {record.status}
            </Tag>
          </Space>
        }
        extra={<Typography.Text type="secondary">{record.trade_date} / {record.model_used || "--"}</Typography.Text>}
      >
        <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }}>
          <Descriptions.Item label="收盘价">{fmtNumber(record.stock_data.close)}</Descriptions.Item>
          <Descriptions.Item label="涨跌幅">
            <span style={{ color: valueColor(record.stock_data.change_pct) }}>{fmtPct(record.stock_data.change_pct)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="换手率">{fmtPct(record.stock_data.turnover_rate)}</Descriptions.Item>
          <Descriptions.Item label="成交额">{fmtAmount(record.stock_data.amount)}</Descriptions.Item>
          <Descriptions.Item label="主力净流入">
            <span style={{ color: valueColor(record.stock_data.main_net_inflow) }}>{fmtAmount(record.stock_data.main_net_inflow)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="量比">{fmtNumber(record.stock_data.volume_ratio)}</Descriptions.Item>
          <Descriptions.Item label="市盈率TTM">{fmtNumber(record.stock_data.pe_ttm)}</Descriptions.Item>
          <Descriptions.Item label="市净率">{fmtNumber(record.stock_data.pb)}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="结构化结论">
        <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="方向判断">{renderDirection(direction)}</Descriptions.Item>
          <Descriptions.Item label="操作建议">{action ? (actionLabels[action] || action) : "--"}</Descriptions.Item>
          <Descriptions.Item label="风险等级">{renderRisk(risk)}</Descriptions.Item>
          <Descriptions.Item label="置信度">
            {confidence == null ? "--" : <Progress percent={Math.round(confidence * 100)} size="small" />}
          </Descriptions.Item>
          <Descriptions.Item label="目标价">{fmtNumber(summaryValue(record, "target_price"))}</Descriptions.Item>
          <Descriptions.Item label="支撑位">{fmtNumber(summaryValue(record, "support_price"))}</Descriptions.Item>
          <Descriptions.Item label="压力位">{fmtNumber(summaryValue(record, "resistance_price"))}</Descriptions.Item>
        </Descriptions>
        {keyFactors(record).length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary">关键因素：</Typography.Text>
            <Space size={[8, 8]} wrap style={{ marginLeft: 8 }}>
              {keyFactors(record).map((item) => <Tag key={item}>{item}</Tag>)}
            </Space>
          </div>
        )}
      </Card>

      <Card title="AI 分析正文">
        <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
          {record.analysis_text || "暂无分析正文"}
        </Typography.Paragraph>
      </Card>

      {record.prediction_text && (
        <Card title="后续判断">
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {record.prediction_text}
          </Typography.Paragraph>
        </Card>
      )}

      {record.recent_news.length > 0 && (
        <Card title="相关新闻">
          <Table
            size="small"
            rowKey={(row, index) => `${row.url || row.title || index}`}
            pagination={false}
            dataSource={record.recent_news}
            columns={[
              { title: "来源", dataIndex: "source", width: 100 },
              { title: "标题", dataIndex: "title", ellipsis: true },
              { title: "时间", dataIndex: "publish_time", width: 160 },
            ]}
          />
        </Card>
      )}
    </Space>
  );
}

export default function StockAnalysis() {
  const [code, setCode] = useState("");
  const [date, setDate] = useState<string | undefined>();
  const [current, setCurrent] = useState<StockAnalysisItem | null>(null);
  const [items, setItems] = useState<StockAnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<StockAnalysisTaskStatus | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeCodeRef = useRef<string>("");

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback((targetCode: string, targetDate: string | undefined) => {
    stopPolling();
    activeCodeRef.current = targetCode;
    pollTimerRef.current = setInterval(async () => {
      try {
        const [statusRes, latestRes] = await Promise.all([
          fetchStockAnalysisTaskStatus(targetCode, targetDate),
          fetchLatestStockAnalysis(targetCode),
        ]);
        setTaskStatus(statusRes);
        if (latestRes) {
          setCurrent(latestRes);
        }
        if (!statusRes.active) {
          stopPolling();
          setGenerating(false);
          if (statusRes.status === "completed") {
            message.success(`个股分析完成：${targetCode}`);
            // 重新加载历史
            fetchStockAnalysisHistory(targetCode, PAGE_SIZE, 0)
              .then((res) => {
                setItems(res.items);
                setTotal(res.total);
                setPage(1);
              })
              .catch(() => {});
          } else if (statusRes.status === "failed") {
            message.error(statusRes.error || "个股分析失败");
            setError(statusRes.error || "个股分析失败");
          }
        }
      } catch {
        // 轮询期间临时错误忽略
      }
    }, 5000);
  }, [stopPolling]);

  const loadHistory = useCallback(async (targetPage = page, targetCode = code.trim()) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchStockAnalysisHistory(targetCode || undefined, PAGE_SIZE, (targetPage - 1) * PAGE_SIZE);
      setItems(res.items);
      setTotal(res.total);
      setPage(targetPage);
    } catch {
      setError("获取个股分析历史失败");
    } finally {
      setLoading(false);
    }
  }, [code, page]);

  const loadLatest = useCallback(async (targetCode = code.trim()) => {
    try {
      const res = await fetchLatestStockAnalysis(targetCode || undefined);
      setCurrent(res);
    } catch {
      setError("获取最新个股分析失败");
    }
  }, [code]);

  useEffect(() => {
    let cancelled = false;

    async function initData() {
      try {
        const [latest, history] = await Promise.all([
          fetchLatestStockAnalysis(),
          fetchStockAnalysisHistory(undefined, PAGE_SIZE, 0),
        ]);
        if (!cancelled) {
          setCurrent(latest);
          setItems(history.items);
          setTotal(history.total);
        }
      } catch {
        if (!cancelled) setError("获取个股分析数据失败");
      }
    }

    initData();
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [stopPolling]);

  const handleGenerate = async () => {
    const targetCode = code.trim();
    if (!targetCode) {
      message.warning("请输入股票代码");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const res = await triggerStockAnalysis(targetCode, date);
      if (res.success) {
        message.success(res.message || "个股分析任务已启动");
        startPolling(targetCode, date);
      } else {
        // already_running 等情况，恢复轮询
        message.warning(res.message || "生成个股分析失败");
        startPolling(targetCode, date);
      }
    } catch {
      message.error("生成个股分析失败");
      setGenerating(false);
    }
  };

  const taskActive = taskStatus?.active === true && activeCodeRef.current === code.trim();
  const taskStage = taskStatus?.stage;

  const columns: ColumnsType<StockAnalysisItem> = [
    {
      title: "生成时间",
      dataIndex: "created_at",
      width: 170,
    },
    {
      title: "交易日",
      dataIndex: "trade_date",
      width: 110,
    },
    {
      title: "代码",
      dataIndex: "code",
      width: 100,
      render: (value: string, record) => <StockLink code={value} name={record.name}>{value}</StockLink>,
    },
    { title: "名称", dataIndex: "name", width: 100 },
    {
      title: "方向",
      width: 90,
      render: (_, record) => renderDirection(summaryValue(record, "direction") as string | undefined),
    },
    {
      title: "置信度",
      width: 120,
      render: (_, record) => {
        const confidence = asNumber(summaryValue(record, "confidence"));
        return confidence == null ? "--" : <Progress percent={Math.round(confidence * 100)} size="small" />;
      },
    },
    {
      title: "风险",
      width: 90,
      render: (_, record) => renderRisk(summaryValue(record, "risk_level") as string | undefined),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (value: string) => (
        <Tag color={value === "completed" ? "green" : value === "failed" ? "red" : "orange"}>{value}</Tag>
      ),
    },
    { title: "模型", dataIndex: "model_used", width: 140, ellipsis: true },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Typography.Title level={4} style={{ margin: 0 }}>AI 个股分析</Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>仅供研究参考，不构成投资建议</Typography.Text>
        </Space>
        <Space>
          <Input
            placeholder="股票代码，如 600519"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleGenerate}
            style={{ width: 180 }}
          />
          <DatePicker
            value={date ? dayjs(date) : undefined}
            onChange={(d) => setDate(d?.format("YYYY-MM-DD"))}
            placeholder="交易日期"
          />
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => { loadLatest(code.trim()); loadHistory(1, code.trim()); }}>
            刷新
          </Button>
          <Button type="primary" icon={<BulbOutlined />} loading={generating} onClick={handleGenerate}>
            生成个股分析
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />}

      {taskActive && (
        <Alert
          type="info"
          showIcon
          icon={<LoadingOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <span>
                正在生成 {code.trim()} 的个股分析
                {taskStage ? ` · 当前阶段：${taskStage}` : ""}
                {taskStatus?.started_at ? ` · 启动于 ${dayjs(taskStatus.started_at).format("HH:mm:ss")}` : ""}
              </span>
              <Progress percent={taskStage ? 60 : 30} status="active" size="small" showInfo={false} />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                若股票当日行情未采集，会先触发数据采集，再调 LLM 分析，整体可能需要 1-3 分钟。可切到其他页面，任务在后台继续跑。
              </Typography.Text>
            </Space>
          }
        />
      )}

      <Spin spinning={loading && !generating}>
        <AnalysisCard record={current} />

        <Card title="历史分析记录" style={{ marginTop: 16 }}>
          <Table
            rowKey="id"
            columns={columns}
            dataSource={items}
            pagination={{
              current: page,
              pageSize: PAGE_SIZE,
              total,
              showSizeChanger: false,
              onChange: (nextPage) => loadHistory(nextPage, code.trim()),
            }}
            onRow={(record) => ({
              onClick: () => setCurrent(record),
              style: { cursor: "pointer" },
            })}
          />
        </Card>
      </Spin>
    </div>
  );
}
