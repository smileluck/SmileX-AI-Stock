import { useState, useEffect, useCallback, useRef } from "react";
import {
  Button,
  Spin,
  Alert,
  Typography,
  Table,
  Tag,
  Card,
  Descriptions,
  Empty,
  Progress,
  message,
  DatePicker,
  Tabs,
  Space,
  Tooltip,
} from "antd";
import { SyncOutlined, BulbOutlined, FireOutlined, RiseOutlined, LoadingOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  fetchLatestTomorrowStrategy,
  fetchTomorrowStrategyByDate,
  fetchTomorrowStrategyTaskStatus,
  triggerTomorrowStrategy,
  type TomorrowStrategyItem,
  type TomorrowStrategySector,
  type TomorrowStrategyStock,
  type TomorrowStrategyTaskStatus,
} from "../api/tomorrowStrategy";
import StockLink from "../components/StockLink";

const POSITIVE_COLOR = "#cf1322";
const NEGATIVE_COLOR = "#3f8600";

function fmtPct(v?: number | null): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtYi(v?: number | null): string {
  if (v == null) return "--";
  return `${v.toFixed(2)}亿`;
}

function fmtPrice(v?: number | null): string {
  if (v == null) return "--";
  return v.toFixed(2);
}

const sustainabilityColor: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "default",
};

const biasColor: Record<string, string> = {
  偏多: "red",
  震荡: "orange",
  偏空: "green",
};

function statusStatusError(s: TomorrowStrategyTaskStatus): string | null {
  if (s.status === "failed" && s.error) return s.error;
  return null;
}

const STAGE_ORDER = [
  "初始化",
  "数据准备",
  "板块/涨停快照",
  "新闻-板块评分",
  "LLM 分析中（最久环节，约 1-3 分钟）",
  "结果解析与落库",
];

function stageToPercent(stage?: string | null): number {
  if (!stage) return 5;
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx < 0) return 50;
  return Math.round(((idx + 1) / STAGE_ORDER.length) * 100);
}

export default function TomorrowStrategy() {
  const [data, setData] = useState<TomorrowStrategyItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [taskStatus, setTaskStatus] = useState<TomorrowStrategyTaskStatus | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollTaskAndData = useCallback(
    async (d: string) => {
      try {
        const [statusRes, dataRes] = await Promise.all([
          fetchTomorrowStrategyTaskStatus(d),
          d === dayjs().format("YYYY-MM-DD")
            ? fetchLatestTomorrowStrategy()
            : fetchTomorrowStrategyByDate(d).catch(() => null),
        ]);
        setTaskStatus(statusRes);
        if (dataRes) {
          setData(dataRes);
        }
        if (!statusRes.active) {
          stopPolling();
          setGenLoading(false);
          if (statusRes.status === "completed") {
            message.success("明日策略生成完成");
          } else if (statusRes.status === "failed") {
            message.error(statusRes.error || "策略生成失败");
            setError(statusStatusError(statusRes));
          }
        }
      } catch {
        // 轮询期间的临时错误不中断
      }
    },
    [stopPolling],
  );

  const startPolling = useCallback(
    (d: string) => {
      stopPolling();
      pollTimerRef.current = setInterval(() => {
        pollTaskAndData(d);
      }, 5000);
    },
    [stopPolling, pollTaskAndData],
  );

  const loadData = useCallback(
    async (d: string) => {
      setLoading(true);
      setError(null);
      try {
        const today = dayjs().format("YYYY-MM-DD");
        let resp: TomorrowStrategyItem | null;
        if (d === today) {
          resp = await fetchLatestTomorrowStrategy();
        } else {
          try {
            resp = await fetchTomorrowStrategyByDate(d);
          } catch (err: unknown) {
            if (err && typeof err === "object" && "response" in err) {
              const r = (err as { response?: { status?: number } }).response;
              if (r?.status === 404) {
                resp = null;
              } else {
                throw err;
              }
            } else {
              throw err;
            }
          }
        }
        setData(resp);

        // 同步检查任务状态：如果上次的任务还在跑，自动恢复轮询
        const statusRes = await fetchTomorrowStrategyTaskStatus(d).catch(() => null);
        if (statusRes) {
          setTaskStatus(statusRes);
          if (statusRes.active) {
            setGenLoading(true);
            startPolling(d);
          } else {
            setGenLoading(false);
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [startPolling],
  );

  useEffect(() => {
    loadData(date);
    return () => stopPolling();
  }, [date, loadData, stopPolling]);

  const handleGenerate = async () => {
    setGenLoading(true);
    setError(null);
    try {
      const resp = await triggerTomorrowStrategy(date);
      if (resp.success) {
        message.success(resp.message || "策略生成任务已启动");
        startPolling(date);
      } else {
        // already_running 等情况
        setError(resp.message || "生成失败");
        message.warning(resp.message || "生成失败");
        // 如果是已在运行，恢复轮询
        startPolling(date);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      message.error(msg);
      setGenLoading(false);
    }
  };

  const sectors = data?.sectors_json || [];
  const stocks = data?.stocks_json || [];
  const advice = data?.strategy_json || {};

  const taskActive = taskStatus?.active === true;
  const taskStage = taskStatus?.stage;

  const stockColumns = [
    {
      title: "代码",
      dataIndex: "code",
      key: "code",
      width: 100,
      render: (v: string, r: TomorrowStrategyStock) =>
        v ? <StockLink code={v} name={r.name}>{v}</StockLink> : "--",
    },
    { title: "名称", dataIndex: "name", key: "name", width: 100 },
    {
      title: "所属板块",
      dataIndex: "sector_name",
      key: "sector_name",
      width: 120,
      render: (v?: string) => v || "--",
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      width: 100,
      render: (v?: string) =>
        v ? <Tag color="blue">{v}</Tag> : "--",
    },
    {
      title: "入场逻辑",
      dataIndex: "entry_logic",
      key: "entry_logic",
      ellipsis: true,
      render: (v?: string) =>
        v ? (
          <Tooltip title={v}>
            <span>{v}</span>
          </Tooltip>
        ) : (
          "--"
        ),
    },
    {
      title: "关注区间",
      key: "watch_range",
      width: 130,
      render: (_: unknown, r: TomorrowStrategyStock) =>
        r.watch_price_low != null && r.watch_price_high != null
          ? `${fmtPrice(r.watch_price_low)} ~ ${fmtPrice(r.watch_price_high)}`
          : "--",
    },
    {
      title: "止损价",
      dataIndex: "stop_loss_price",
      key: "stop_loss_price",
      width: 80,
      render: (v?: number | null) => fmtPrice(v),
    },
    {
      title: "目标价",
      dataIndex: "target_price",
      key: "target_price",
      width: 80,
      render: (v?: number | null) => fmtPrice(v),
    },
    {
      title: "风险标签",
      dataIndex: "risk_tags",
      key: "risk_tags",
      width: 140,
      render: (tags?: string[]) =>
        tags && tags.length > 0 ? (
          tags.map((t) => (
            <Tag key={t} color="default" style={{ marginBottom: 2 }}>
              {t}
            </Tag>
          ))
        ) : (
          "--"
        ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Space>
          <Typography.Title level={4} style={{ margin: 0 }}>
            明日板块策略
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            自动生成：工作日 15:40（基于收盘板块+热点事件+候选股池）
          </Typography.Text>
        </Space>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => {
              const ds = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD");
              setDate(ds);
            }}
            size="small"
          />
          <Button
            icon={<SyncOutlined spin={loading} />}
            onClick={() => loadData(date)}
            size="small"
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            loading={genLoading}
            onClick={handleGenerate}
            size="small"
          >
            重新生成
          </Button>
        </div>
      </div>

      {error && (
        <Alert
          message={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          closable
          onClose={() => setError(null)}
        />
      )}

      {taskActive && (
        <Alert
          type="info"
          showIcon
          icon={<LoadingOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <span>
                正在生成明日策略
                {taskStage ? ` · 当前阶段：${taskStage}` : ""}
                {taskStatus?.started_at
                  ? ` · 启动于 ${dayjs(taskStatus.started_at).format("HH:mm:ss")}`
                  : ""}
              </span>
              <Progress
                percent={stageToPercent(taskStage)}
                status="active"
                size="small"
                showInfo={false}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                LLM 分析是最耗时的环节（约 1-3 分钟），请耐心等待。可切到其他页面，任务在后台继续跑。
              </Typography.Text>
            </Space>
          }
        />
      )}

      <Spin spinning={loading && !data}>
        {!data ? (
          <Empty
            description={
              <span>
                {loading ? "加载中..." : date === dayjs().format("YYYY-MM-DD")
                  ? "暂无明日策略，点「重新生成」立即创建"
                  : `${date} 暂无数据`}
              </span>
            }
          />
        ) : (
          <>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Descriptions size="small" column={4}>
                <Descriptions.Item label="交易日期">{data.trade_date}</Descriptions.Item>
                <Descriptions.Item label="生成时间">
                  {dayjs(data.updated_at).format("YYYY-MM-DD HH:mm")}
                </Descriptions.Item>
                <Descriptions.Item label="模型">
                  <Tag>{data.model_used || "--"}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="板块/个股">
                  <Tag color="red">{sectors.length} 板块</Tag>
                  <Tag color="blue">{stocks.length} 个股</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Tabs
              defaultActiveKey="sectors"
              items={[
                {
                  key: "sectors",
                  label: (
                    <span>
                      <FireOutlined /> 推荐板块 TOP{sectors.length || 5}
                    </span>
                  ),
                  children: (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
                        gap: 12,
                      }}
                    >
                      {sectors.length === 0 ? (
                        <Empty description="暂无板块推荐" />
                      ) : (
                        sectors.map((s, idx) => (
                          <SectorCard key={`${s.code}-${idx}`} sector={s} />
                        ))
                      )}
                    </div>
                  ),
                },
                {
                  key: "stocks",
                  label: (
                    <span>
                      <RiseOutlined /> 代表个股 ({stocks.length})
                    </span>
                  ),
                  children:
                    stocks.length === 0 ? (
                      <Empty description="暂无个股推荐" />
                    ) : (
                      <Table
                        dataSource={stocks}
                        columns={stockColumns}
                        rowKey={(r, i) => `${r.code}-${i}`}
                        size="small"
                        pagination={{ pageSize: 20, showSizeChanger: false }}
                        scroll={{ x: 1100 }}
                      />
                    ),
                },
                {
                  key: "advice",
                  label: "策略建议",
                  children: (
                    <div>
                      <Card size="small" style={{ marginBottom: 12 }}>
                        <Descriptions size="small" column={3} bordered>
                          <Descriptions.Item label="仓位建议">
                            {advice.position_level ? (
                              <Tag color="volcano">{advice.position_level}</Tag>
                            ) : (
                              "--"
                            )}
                          </Descriptions.Item>
                          <Descriptions.Item label="操作风格">
                            {advice.style ? <Tag color="geekblue">{advice.style}</Tag> : "--"}
                          </Descriptions.Item>
                          <Descriptions.Item label="市场倾向">
                            {advice.market_bias ? (
                              <Tag color={biasColor[advice.market_bias] || "default"}>
                                {advice.market_bias}
                              </Tag>
                            ) : (
                              "--"
                            )}
                          </Descriptions.Item>
                        </Descriptions>
                      </Card>
                      {advice.risk_warnings && advice.risk_warnings.length > 0 && (
                        <Alert
                          type="warning"
                          showIcon
                          message="风险提示"
                          description={
                            <ul style={{ margin: 0, paddingLeft: 18 }}>
                              {advice.risk_warnings.map((w, i) => (
                                <li key={i}>{w}</li>
                              ))}
                            </ul>
                          }
                          style={{ marginBottom: 12 }}
                        />
                      )}
                      {advice.actionable_summary && (
                        <Card size="small" title="明日操作策略">
                          <Typography.Paragraph
                            style={{ whiteSpace: "pre-wrap", margin: 0 }}
                          >
                            {advice.actionable_summary}
                          </Typography.Paragraph>
                        </Card>
                      )}
                    </div>
                  ),
                },
                {
                  key: "raw",
                  label: "原始报告",
                  children: (
                    <Card size="small">
                      <Typography.Paragraph
                        style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12 }}
                      >
                        {data.raw_text || "（无原始文本）"}
                      </Typography.Paragraph>
                    </Card>
                  ),
                },
              ]}
            />
          </>
        )}
      </Spin>
    </div>
  );
}

function SectorCard({ sector }: { sector: TomorrowStrategySector }) {
  const changeColor =
    sector.change_pct_today != null
      ? sector.change_pct_today >= 0
        ? POSITIVE_COLOR
        : NEGATIVE_COLOR
      : "#666";

  return (
    <Card
      size="small"
      title={
        <Space>
          {sector.rank ? (
            <Tag color={sector.rank <= 3 ? "red" : "default"}>#{sector.rank}</Tag>
          ) : null}
          <span>{sector.name || sector.code || "--"}</span>
          <Tag>{sector.sector_type === "industry" ? "行业" : sector.sector_type === "concept" ? "概念" : sector.sector_type || "--"}</Tag>
        </Space>
      }
    >
      <Descriptions size="small" column={2} style={{ marginBottom: 8 }}>
        <Descriptions.Item label="今日涨幅">
          <span style={{ color: changeColor, fontWeight: 600 }}>
            {fmtPct(sector.change_pct_today)}
          </span>
        </Descriptions.Item>
        <Descriptions.Item label="连续上涨">
          {sector.streak_up_days != null && sector.streak_up_days > 0 ? (
            <Tag color="red">{sector.streak_up_days} 日</Tag>
          ) : (
            <span>--</span>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="主力净流入">
          <span style={{ color: POSITIVE_COLOR }}>{fmtYi(sector.main_net_inflow_yi)}</span>
        </Descriptions.Item>
        <Descriptions.Item label="新闻热度">
          {sector.news_count ? (
            <Tag color="orange">
              {sector.news_count}条 / 均分{sector.news_avg_score?.toFixed(1) ?? "--"}
            </Tag>
          ) : (
            <span>--</span>
          )}
        </Descriptions.Item>
      </Descriptions>

      {sector.top_events && sector.top_events.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            关联事件：
          </Typography.Text>
          <ul style={{ margin: "4px 0 0 0", paddingLeft: 18, fontSize: 12 }}>
            {sector.top_events.slice(0, 3).map((e, i) => (
              <li key={i}>
                <span>[{e.source || "--"}] {e.title || "--"}</span>
                {e.impact ? (
                  <Tag style={{ marginLeft: 4, fontSize: 11 }}>{e.impact}</Tag>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ marginBottom: 8 }}>
        <Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            持续性：
          </Typography.Text>
          <Tag color={sustainabilityColor[sector.sustainability || ""] || "default"}>
            {sector.sustainability === "high"
              ? "强"
              : sector.sustainability === "medium"
              ? "中"
              : sector.sustainability === "low"
              ? "弱"
              : "--"}
          </Tag>
        </Space>
        {sector.sustainability_reason ? (
          <Typography.Paragraph
            style={{ fontSize: 12, margin: "4px 0 0 0", color: "#666" }}
          >
            {sector.sustainability_reason}
          </Typography.Paragraph>
        ) : null}
      </div>

      {sector.tomorrow_outlook ? (
        <Alert
          type="info"
          showIcon
          message={
            <span style={{ fontSize: 12 }}>
              <b>明日展望：</b>
              {sector.tomorrow_outlook}
            </span>
          }
          style={{ padding: "4px 12px" }}
        />
      ) : null}
    </Card>
  );
}
