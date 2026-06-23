import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Card, Tabs, Form, Select, Radio, DatePicker, InputNumber, Button, Table, Tag,
  Statistic, Row, Col, Alert, Progress, Space, message, Tooltip, Modal, Input,
} from "antd";
import type { TabsProps } from "antd";
import { PlayCircleOutlined, DeleteOutlined, ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import ReactECharts from "echarts-for-react";

import {
  fetchStrategies, fetchDataCoverage, createBacktest, listBacktestRuns,
  getBacktestRun, listBacktestTrades, deleteBacktestRun, triggerBackfill,
  fetchBackfillStatus,
} from "../api/backtest";
import type {
  StrategyInfo, BacktestRequest, BacktestDetail, BacktestRunMeta, TradeItem,
  BacktestMetrics,
} from "../api/backtest";

const { RangePicker } = DatePicker;

type StrategyType = "morning" | "midday" | "afternoon" | "custom_factor";
type Universe = "all" | "main" | "sh_main" | "sz_main" | "gem" | "star" | "watchlist";

const UNIVERSE_OPTIONS = [
  { label: "沪深主板", value: "main" },
  { label: "沪市主板", value: "sh_main" },
  { label: "深市主板", value: "sz_main" },
  { label: "创业板", value: "gem" },
  { label: "科创板", value: "star" },
  { label: "自选股", value: "watchlist" },
  { label: "全市场", value: "all" },
];

const STRATEGY_LABEL: Record<string, string> = {
  morning: "早盘",
  midday: "午盘",
  afternoon: "尾盘",
  custom_factor: "自定义因子",
};

const STRATEGY_COLOR: Record<string, string> = {
  morning: "#f5222d",
  midday: "#fa8c16",
  afternoon: "#52c41a",
  custom_factor: "#1677ff",
};

export default function Backtest() {
  return (
    <div style={{ padding: 16 }}>
      <Tabs
        defaultActiveKey="new"
        items={[
          { key: "new", label: "新建回测", children: <NewBacktestTab /> },
          { key: "history", label: "历史回测", children: <HistoryTab /> },
          { key: "compare", label: "策略对比", children: <CompareTab /> },
        ]}
      />
    </div>
  );
}

// ============ Tab 1: 新建回测 ============

function NewBacktestTab() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [coverage, setCoverage] = useState<{ n_days: number; sufficient: boolean; min_date: string | null; max_date: string | null } | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestDetail | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState<string>("");
  const backfillTimerRef = useRef<number | null>(null);

  const [form] = Form.useForm();
  const strategyType = Form.useWatch("strategy_type", form) as StrategyType | undefined;

  // 加载策略列表 + 数据覆盖度
  useEffect(() => {
    (async () => {
      try {
        const [strats, cov] = await Promise.all([
          fetchStrategies(),
          fetchDataCoverage("main"),
        ]);
        setStrategies(strats);
        setCoverage(cov);
        if (strats.length > 0) {
          form.setFieldsValue({
            strategy_type: "midday",
            universe: "main",
            date_range: [dayjs().subtract(60, "day"), dayjs()],
            initial_capital: 100000,
            top_n: 5,
            rebalance: "daily",
            stop_loss: -0.07,
            take_profit: 0.15,
            commission_bps: 2.5,
            stamp_duty_bps: 1.0,
            benchmark: "hs300",
          });
        }
      } catch {
        message.error("初始化失败，请检查后端服务");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 数据覆盖度刷新
  const refreshCoverage = useCallback(async (universe: Universe = "main") => {
    try {
      const cov = await fetchDataCoverage(universe);
      setCoverage(cov);
    } catch { /* ignore */ }
  }, []);

  // 一键补数
  const handleBackfill = useCallback(async () => {
    setBackfilling(true);
    setBackfillMsg("启动 backfill...");
    try {
      const res = await triggerBackfill(365);
      if (!res.task_id) {
        message.error(res.message);
        setBackfilling(false);
        return;
      }
      // 轮询
      const taskId = res.task_id;
      const poll = async () => {
        try {
          const s = await fetchBackfillStatus(taskId);
          setBackfillMsg(`[${s.status}] ${s.message}`);
          if (s.status === "done" || s.status === "failed") {
            setBackfilling(false);
            if (backfillTimerRef.current) {
              window.clearInterval(backfillTimerRef.current);
              backfillTimerRef.current = null;
            }
            if (s.status === "done") {
              message.success("补数完成");
              refreshCoverage();
            } else {
              message.error("补数失败：" + s.message);
            }
          }
        } catch { /* ignore */ }
      };
      poll();
      backfillTimerRef.current = window.setInterval(poll, 5000);
    } catch (e) {
      setBackfilling(false);
      message.error("补数启动失败");
    }
  }, [refreshCoverage]);

  useEffect(() => {
    return () => {
      if (backfillTimerRef.current) window.clearInterval(backfillTimerRef.current);
    };
  }, []);

  // 提交回测
  const handleSubmit = useCallback(async (values: unknown) => {
    const v = values as {
      strategy_type: StrategyType;
      universe: Universe;
      date_range: [Dayjs, Dayjs];
      initial_capital: number;
      top_n: number;
      rebalance: string;
      stop_loss: number;
      take_profit: number;
      commission_bps: number;
      stamp_duty_bps: number;
      benchmark: string;
      custom_factors?: Record<string, number>;
      name?: string;
    };
    setRunning(true);
    setResult(null);
    try {
      const req: BacktestRequest = {
        strategy_type: v.strategy_type,
        universe: v.universe,
        start_date: v.date_range[0].format("YYYY-MM-DD"),
        end_date: v.date_range[1].format("YYYY-MM-DD"),
        initial_capital: v.initial_capital,
        top_n: v.top_n,
        rebalance: v.rebalance,
        stop_loss: v.stop_loss,
        take_profit: v.take_profit,
        commission_bps: v.commission_bps,
        stamp_duty_bps: v.stamp_duty_bps,
        benchmark: v.benchmark,
        custom_factors: v.custom_factors,
        name: v.name,
      };
      const detail = await createBacktest(req);
      setResult(detail);
      message.success(`回测完成，共 ${detail.metrics.n_days ?? 0} 个交易日`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "回测失败");
    } finally {
      setRunning(false);
    }
  }, []);

  return (
    <div>
      {coverage && !coverage.sufficient && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`当前数据深度仅 ${coverage.n_days} 个交易日（${coverage.min_date} ~ ${coverage.max_date}）`}
          description={
            <Space>
              <span>建议至少 60 天数据才能产生有意义的回测结果。</span>
              <Button
                type="primary"
                danger
                size="small"
                icon={<ThunderboltOutlined />}
                loading={backfilling}
                onClick={handleBackfill}
              >
                一键补数（全市场 365 天）
              </Button>
              {backfillMsg && <Tag color="processing">{backfillMsg}</Tag>}
            </Space>
          }
        />
      )}

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="策略配置" size="small">
            <Form form={form} layout="vertical" onFinish={handleSubmit}>
              <Form.Item label="策略类型" name="strategy_type" rules={[{ required: true }]}>
                <Select
                  options={strategies.map((s) => ({
                    label: s.experimental ? `${s.label}（实验性）` : s.label,
                    value: s.type,
                  }))}
                />
              </Form.Item>
              <Form.Item label="股票池" name="universe" rules={[{ required: true }]}>
                <Radio.Group options={UNIVERSE_OPTIONS} optionType="button" buttonStyle="solid" />
              </Form.Item>
              <Form.Item label="回测区间" name="date_range" rules={[{ required: true }]}>
                <RangePicker style={{ width: "100%" }} />
              </Form.Item>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="初始资金" name="initial_capital">
                    <InputNumber style={{ width: "100%" }} min={10000} step={10000} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="持仓数 (TopN)" name="top_n">
                    <InputNumber style={{ width: "100%" }} min={1} max={20} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="调仓周期" name="rebalance">
                    <Select
                      options={[
                        { label: "每日", value: "daily" },
                        { label: "每周", value: "weekly" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="基准" name="benchmark">
                    <Select
                      options={[
                        { label: "沪深300", value: "hs300" },
                        { label: "上证50", value: "sz50" },
                        { label: "创业板指", value: "czb" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="止损率（如 -0.07 = -7%）" name="stop_loss">
                    <InputNumber style={{ width: "100%" }} step={0.01} min={-0.5} max={0} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="止盈率" name="take_profit">
                    <InputNumber style={{ width: "100%" }} step={0.01} min={0} max={1} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="佣金（万分之）" name="commission_bps">
                    <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="印花税（千分之）" name="stamp_duty_bps">
                    <InputNumber style={{ width: "100%" }} step={0.1} min={0} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="回测名称（可选）" name="name">
                <Input placeholder="例如：午盘策略-2025年Q1" />
              </Form.Item>

              {strategyType === "custom_factor" && <CustomFactorFields />}

              <Button
                type="primary"
                htmlType="submit"
                icon={<PlayCircleOutlined />}
                loading={running}
                block
              >
                {running ? "回测中..." : "开始回测"}
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          {running && (
            <Card style={{ marginBottom: 12 }}>
              <Progress percent={70} status="active" strokeColor={{ from: "#108ee9", to: "#87d068" }} />
              <p style={{ textAlign: "center", color: "#888", marginTop: 8 }}>
                正在执行回测，请稍候...
              </p>
            </Card>
          )}
          {result && <ResultPanel detail={result} />}
        </Col>
      </Row>
    </div>
  );
}

function CustomFactorFields() {
  return (
    <Card size="small" title="自定义因子权重（总和为 1）" style={{ marginBottom: 12 }}>
      <Row gutter={8}>
        <Col span={12}>
          <Form.Item label="主力净流入率" name={["custom_factors", "main_net_inflow_pct"]} initialValue={0.3}>
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} max={1} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="涨幅" name={["custom_factors", "change_pct"]} initialValue={0.2}>
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} max={1} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="换手率（适中）" name={["custom_factors", "turnover_rate"]} initialValue={0.2}>
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} max={1} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="低 PE" name={["custom_factors", "neg_pe"]} initialValue={0.3}>
            <InputNumber style={{ width: "100%" }} step={0.1} min={0} max={1} />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );
}

function ResultPanel({ detail }: { detail: BacktestDetail }) {
  const m = detail.metrics;
  return (
    <div>
      <Card title={`回测结果：${detail.name}`} size="small" style={{ marginBottom: 12 }}
        extra={<Tag color={m.total_return && m.total_return > 0 ? "green" : "red"}>{detail.strategy_type}</Tag>}
      >
        <Row gutter={[8, 8]}>
          <Col xs={12} md={8}>
            <Statistic
              title="累计收益"
              value={m.total_return ?? 0}
              precision={2}
              suffix="%"
              valueStyle={{ color: (m.total_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}
            />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="年化收益" value={m.annual_return ?? 0} precision={2} suffix="%"
              valueStyle={{ color: (m.annual_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="最大回撤" value={m.max_drawdown ?? 0} precision={2} suffix="%"
              valueStyle={{ color: "#cf1322" }} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="夏普比率" value={m.sharpe ?? 0} precision={3} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="卡玛比率" value={m.calmar ?? 0} precision={3} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="胜率" value={m.win_rate ?? 0} precision={2} suffix="%" />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="盈亏比" value={m.profit_loss_ratio ?? 0} precision={3} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="超额收益(vs基准)" value={m.excess_return ?? 0} precision={2} suffix="%"
              valueStyle={{ color: (m.excess_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }} />
          </Col>
          <Col xs={12} md={8}>
            <Statistic title="交易笔数" value={m.n_trades ?? 0} suffix={`/ ${m.n_sells ?? 0}卖`} />
          </Col>
        </Row>
      </Card>

      <EquityChart detail={detail} />
    </div>
  );
}

function EquityChart({ detail }: { detail: BacktestDetail }) {
  const option = useMemo(() => {
    const dates = detail.equity_curve.map((e) => e.trade_date);
    const initial = (detail.params.initial_capital as number) || 100000;
    const strategyNav = detail.equity_curve.map((e) => e.equity / initial);
    const benchmark = detail.equity_curve.map((e) => e.benchmark);
    const drawdown = detail.equity_curve.map((e) => (e.drawdown ?? 0) * 100);

    return {
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      legend: { data: ["策略净值", "沪深300", "回撤%"] },
      grid: { left: 50, right: 50, top: 40, bottom: 60 },
      xAxis: { type: "category", data: dates, axisLabel: { formatter: (v: string) => v.slice(5) } },
      yAxis: [
        { type: "value", name: "净值", scale: true },
        { type: "value", name: "回撤%", min: () => Math.min(...drawdown, -5), max: 0 },
      ],
      dataZoom: [
        { type: "inside", start: 0, end: 100 },
        { type: "slider", bottom: 10 },
      ],
      series: [
        {
          name: "策略净值",
          type: "line",
          data: strategyNav,
          showSymbol: false,
          lineStyle: { width: 2, color: STRATEGY_COLOR[detail.strategy_type] || "#1677ff" },
        },
        {
          name: "沪深300",
          type: "line",
          data: benchmark,
          showSymbol: false,
          lineStyle: { width: 1, color: "#999", type: "dashed" },
        },
        {
          name: "回撤%",
          type: "line",
          yAxisIndex: 1,
          data: drawdown,
          showSymbol: false,
          areaStyle: { color: "rgba(245,34,45,0.15)" },
          lineStyle: { color: "#f5222d", width: 1 },
        },
      ],
    };
  }, [detail]);

  const [tradesOpen, setTradesOpen] = useState(false);
  const [trades, setTrades] = useState<{ items: TradeItem[]; total: number } | null>(null);

  const showTrades = useCallback(async () => {
    try {
      const res = await listBacktestTrades(detail.id, 200, 0);
      setTrades(res);
      setTradesOpen(true);
    } catch {
      message.error("获取交易明细失败");
    }
  }, [detail.id]);

  return (
    <Card
      title="资金曲线 / 回撤"
      size="small"
      style={{ marginBottom: 12 }}
      extra={<Button size="small" onClick={showTrades}>查看交易明细</Button>}
    >
      <ReactECharts option={option} style={{ height: 380 }} />
      <Modal
        open={tradesOpen}
        title={`交易明细 (共 ${trades?.total ?? 0} 笔)`}
        footer={null}
        onCancel={() => setTradesOpen(false)}
        width={900}
      >
        <Table<TradeItem>
          size="small"
          dataSource={trades?.items ?? []}
          rowKey={(r) => `${r.trade_date}-${r.code}-${r.side}-${r.shares}-${Math.random()}`}
          pagination={{ pageSize: 15, size: "small" }}
          columns={[
            { title: "日期", dataIndex: "trade_date", key: "trade_date" },
            { title: "代码", dataIndex: "code", key: "code" },
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "方向", dataIndex: "side", key: "side",
              render: (s: string) => <Tag color={s === "buy" ? "green" : "volcano"}>{s === "buy" ? "买" : "卖"}</Tag>,
            },
            { title: "价格", dataIndex: "price", key: "price", render: (v: number) => v.toFixed(2) },
            { title: "股数", dataIndex: "shares", key: "shares" },
            {
              title: "金额", dataIndex: "amount", key: "amount",
              render: (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }),
            },
            { title: "费用", dataIndex: "cost", key: "cost", render: (v: number) => v.toFixed(2) },
            { title: "原因", dataIndex: "reason", key: "reason",
              render: (r: string) => {
                const colorMap: Record<string, string> = {
                  signal: "blue", rebalance: "orange",
                  stop_loss: "red", take_profit: "green",
                };
                return <Tag color={colorMap[r] || "default"}>{r}</Tag>;
              } },
          ]}
        />
      </Modal>
    </Card>
  );
}

// ============ Tab 2: 历史回测 ============

function HistoryTab() {
  const [runs, setRuns] = useState<BacktestRunMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const load = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const res = await listBacktestRuns(20, (p - 1) * 20);
      setRuns(res.items);
      setTotal(res.total);
      setPage(p);
    } catch {
      message.error("加载历史回测失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(1); }, [load]);

  const handleDelete = useCallback(async (id: number) => {
    Modal.confirm({
      title: "确认删除该回测？",
      content: "删除后不可恢复，所有交易明细和资金曲线都会被清除。",
      okType: "danger",
      onOk: async () => {
        try {
          await deleteBacktestRun(id);
          message.success("已删除");
          load(page);
        } catch {
          message.error("删除失败");
        }
      },
    });
  }, [load, page]);

  const columns = [
    { title: "ID", dataIndex: "id", key: "id", width: 60 },
    { title: "名称", dataIndex: "name", key: "name" },
    {
      title: "策略", dataIndex: "strategy_type", key: "strategy_type",
      render: (s: string) => <Tag color={STRATEGY_COLOR[s] || "default"}>{STRATEGY_LABEL[s] || s}</Tag>,
    },
    { title: "区间", key: "range",
      render: (_: unknown, r: BacktestRunMeta) => `${r.start_date} ~ ${r.end_date}` },
    {
      title: "累计收益", key: "total_return",
      render: (_: unknown, r: BacktestRunMeta) => (
        <span style={{ color: (r.metrics.total_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}>
          {(r.metrics.total_return ?? 0).toFixed(2)}%
        </span>
      ),
    },
    {
      title: "年化", key: "annual",
      render: (_: unknown, r: BacktestRunMeta) => (
        <span style={{ color: (r.metrics.annual_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}>
          {(r.metrics.annual_return ?? 0).toFixed(2)}%
        </span>
      ),
    },
    {
      title: "夏普", key: "sharpe",
      render: (_: unknown, r: BacktestRunMeta) => (r.metrics.sharpe ?? 0).toFixed(3),
    },
    {
      title: "最大回撤", key: "mdd",
      render: (_: unknown, r: BacktestRunMeta) => (
        <span style={{ color: "#cf1322" }}>{(r.metrics.max_drawdown ?? 0).toFixed(2)}%</span>
      ),
    },
    { title: "创建时间", dataIndex: "created_at", key: "created_at",
      render: (v: string) => v?.slice(0, 16) },
    {
      title: "操作", key: "actions", width: 100,
      render: (_: unknown, r: BacktestRunMeta) => (
        <Space>
          <Tooltip title="删除">
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <Card
      size="small"
      title={`历史回测（共 ${total} 条）`}
      extra={<Button icon={<ReloadOutlined />} onClick={() => load(page)}>刷新</Button>}
    >
      <Table<BacktestRunMeta>
        columns={columns}
        dataSource={runs}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => load(p),
          showSizeChanger: false,
        }}
      />
    </Card>
  );
}

// ============ Tab 3: 策略对比 ============

function CompareTab() {
  const [runs, setRuns] = useState<BacktestRunMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [details, setDetails] = useState<BacktestDetail[]>([]);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listBacktestRuns(50, 0);
      setRuns(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (selected.length === 0) {
      setDetails([]);
      return;
    }
    setLoadingDetails(true);
    Promise.all(selected.map((id) => getBacktestRun(id)))
      .then(setDetails)
      .catch(() => message.error("加载详情失败"))
      .finally(() => setLoadingDetails(false));
  }, [selected]);

  const chartOption = useMemo(() => {
    if (details.length === 0) return {};
    const dates = details[0].equity_curve.map((e) => e.trade_date);
    const series = details.map((d) => {
      const initial = (d.params.initial_capital as number) || 100000;
      return {
        name: `${d.id} - ${d.name}`,
        type: "line",
        data: d.equity_curve.map((e) => e.equity / initial),
        showSymbol: false,
        lineStyle: { width: 2 },
      };
    });
    return {
      tooltip: { trigger: "axis" },
      legend: { top: 5 },
      grid: { left: 50, right: 30, top: 50, bottom: 50 },
      xAxis: { type: "category", data: dates,
        axisLabel: { formatter: (v: string) => v.slice(5) } },
      yAxis: { type: "value", scale: true, name: "净值" },
      dataZoom: [{ type: "inside" }, { type: "slider" }],
      series,
    };
  }, [details]);

  return (
    <Card
      size="small"
      title="策略对比（多选 2-4 个回测叠加资金曲线）"
    >
      <Select
        mode="multiple"
        style={{ width: "100%", marginBottom: 12 }}
        placeholder="选择 2-4 个回测任务"
        value={selected}
        onChange={setSelected}
        loading={loading}
        options={runs.map((r) => ({
          label: `#${r.id} ${r.name} (累计 ${(r.metrics.total_return ?? 0).toFixed(1)}%)`,
          value: r.id,
        }))}
        maxTagCount={5}
      />

      {loadingDetails && <Progress percent={90} status="active" />}

      {details.length >= 2 && (
        <ReactECharts option={chartOption} style={{ height: 400 }} />
      )}

      {details.length >= 2 && (
        <Table<BacktestDetail>
          size="small"
          style={{ marginTop: 12 }}
          rowKey="id"
          pagination={false}
          dataSource={details}
          columns={[
            { title: "ID", dataIndex: "id", key: "id", width: 60 },
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "策略", dataIndex: "strategy_type", key: "strategy_type",
              render: (s: string) => <Tag color={STRATEGY_COLOR[s] || "default"}>{STRATEGY_LABEL[s] || s}</Tag>,
            },
            ...metricColumns(),
          ]}
        />
      )}
    </Card>
  );
}

function metricColumns() {
  const fmt = (m: BacktestMetrics, key: keyof BacktestMetrics, suffix = "", precision = 2) => {
    const v = (m[key] as number | undefined) ?? 0;
    return v.toFixed(precision) + suffix;
  };
  return [
    {
      title: "累计收益", key: "tr",
      render: (_: unknown, r: BacktestDetail) => (
        <span style={{ color: (r.metrics.total_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}>
          {fmt(r.metrics, "total_return", "%")}
        </span>
      ),
    },
    {
      title: "年化", key: "ar",
      render: (_: unknown, r: BacktestDetail) => (
        <span style={{ color: (r.metrics.annual_return ?? 0) >= 0 ? "#3f8600" : "#cf1322" }}>
          {fmt(r.metrics, "annual_return", "%")}
        </span>
      ),
    },
    {
      title: "夏普", key: "sh",
      render: (_: unknown, r: BacktestDetail) => fmt(r.metrics, "sharpe", "", 3),
    },
    {
      title: "最大回撤", key: "mdd",
      render: (_: unknown, r: BacktestDetail) => (
        <span style={{ color: "#cf1322" }}>{fmt(r.metrics, "max_drawdown", "%")}</span>
      ),
    },
    {
      title: "胜率", key: "wr",
      render: (_: unknown, r: BacktestDetail) => fmt(r.metrics, "win_rate", "%"),
    },
  ];
}
