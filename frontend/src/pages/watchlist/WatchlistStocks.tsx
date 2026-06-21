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
  Modal,
  Input,
  List,
  Dropdown,
  Space,
  Empty,
  InputNumber,
  Form,
  Popconfirm,
  Select,
} from "antd";
import {
  PlusOutlined,
  SyncOutlined,
  BulbOutlined,
  DownOutlined,
  SearchOutlined,
  DeleteOutlined,
  StarOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import {
  fetchWatchlistStocks,
  addWatchlistStock,
  patchWatchlistStock,
  deleteWatchlistStock,
  searchWatchlistStock,
  triggerWatchlistSnapshot,
  generateWatchlistAnalysis,
  fetchWatchlistAnalysisTaskStatus,
} from "../../api/watchlist";
import type {
  WatchlistStockResponse,
  WatchlistStockItem,
  WatchlistSearchItem,
  WatchlistAnalysisTaskStatus,
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

function pctColor(v: number | null | undefined): string {
  if (v == null) return "default";
  if (v > 0) return POS_COLOR;
  if (v < 0) return NEG_COLOR;
  return "default";
}

const actionConfig: Record<string, { color: string; label: string }> = {
  buy: { color: "red", label: "建议买入" },
  wait: { color: "orange", label: "观望" },
  avoid: { color: "green", label: "回避" },
};

export default function WatchlistStocks() {
  const navigate = useNavigate();
  const [data, setData] = useState<WatchlistStockResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tradeDate] = useState<string>(dayjs().format("YYYY-MM-DD"));

  // 添加 Modal
  const [addOpen, setAddOpen] = useState(false);
  const [searchKw, setSearchKw] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<WatchlistSearchItem[]>();
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 设置 Modal
  const [settingItem, setSettingItem] = useState<WatchlistStockItem | null>(null);
  const [settingForm] = Form.useForm();
  const [settingSaving, setSettingSaving] = useState(false);

  // 任务进度（早盘/收盘共用）
  const [activePhase, setActivePhase] = useState<"morning" | "close" | null>(null);
  const [taskStatus, setTaskStatus] = useState<WatchlistAnalysisTaskStatus | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (phase: "morning" | "close") => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const [status, fresh] = await Promise.all([
            fetchWatchlistAnalysisTaskStatus(tradeDate, phase),
            fetchWatchlistStocks(tradeDate),
          ]);
          setTaskStatus(status);
          setData(fresh);
          if (!status.active) {
            stopPolling();
            setAnalysisLoading(false);
            setActivePhase(null);
            if (status.status === "completed") {
              message.success(`${phase === "morning" ? "早盘" : "收盘"}分析完成（共 ${status.total} 只）`);
            } else if (status.status === "failed") {
              message.error(status.error || "分析失败");
            }
          }
        } catch {
          // 忽略临时错误
        }
      }, 5000);
    },
    [tradeDate, stopPolling],
  );

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWatchlistStocks(tradeDate);
      setData(res);
    } catch {
      setError("获取自选股列表失败");
    } finally {
      setLoading(false);
    }
  }, [tradeDate]);

  useEffect(() => {
    loadData();
    return () => stopPolling();
  }, [loadData, stopPolling]);

  // 搜索防抖
  const doSearch = (kw: string) => {
    if (!kw.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    searchWatchlistStock(kw.trim())
      .then(setSearchResults)
      .catch(() => setSearchResults([]))
      .finally(() => setSearching(false));
  };

  const onSearchChange = (v: string) => {
    setSearchKw(v);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => doSearch(v), 350);
  };

  const handleAddByCode = async (code: string) => {
    try {
      await addWatchlistStock({ code });
      message.success(`已添加 ${code}`);
      loadData();
    } catch {
      message.error("添加失败");
    }
  };

  const handleAddFromResult = async (item: WatchlistSearchItem) => {
    try {
      await addWatchlistStock({
        code: item.code,
        name: item.name,
        add_price: item.price,
      });
      message.success(`已添加 ${item.name || item.code}（添加价 ${fmtPrice(item.price)}）`);
      loadData();
    } catch {
      message.error("添加失败");
    }
  };

  const handleDelete = async (code: string) => {
    try {
      await deleteWatchlistStock(code);
      message.success("已移除");
      loadData();
    } catch {
      message.error("移除失败");
    }
  };

  const handleSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      const res = await triggerWatchlistSnapshot(tradeDate);
      message.success(`快照完成：成功 ${res.success}/${res.total}，失败 ${res.failed}`);
      loadData();
    } catch {
      message.error("快照失败");
    } finally {
      setSnapshotLoading(false);
    }
  };

  const handleAnalyze = async (phase: "morning" | "close") => {
    setAnalysisLoading(true);
    setActivePhase(phase);
    setError(null);
    try {
      const res = await generateWatchlistAnalysis(phase, tradeDate);
      if (res.no_data) {
        message.warning("暂无关注股（status=watching），请先添加");
        setAnalysisLoading(false);
        setActivePhase(null);
        return;
      }
      if (res.already_running) {
        message.info(`已有${phase === "morning" ? "早盘" : "收盘"}分析在跑，继续轮询`);
      } else {
        message.success(`${phase === "morning" ? "早盘" : "收盘"}分析任务已启动（共 ${res.total} 只）`);
      }
      startPolling(phase);
    } catch {
      message.error("启动分析失败");
      setAnalysisLoading(false);
      setActivePhase(null);
    }
  };

  const openSetting = (item: WatchlistStockItem) => {
    setSettingItem(item);
    settingForm.setFieldsValue({
      target_buy_price: item.target_buy_price ?? null,
      stop_loss_price: item.stop_loss_price ?? null,
      note: item.note ?? "",
      status: item.status ?? "watching",
    });
  };

  const handleSettingSave = async () => {
    if (!settingItem) return;
    try {
      const values = await settingForm.validateFields();
      setSettingSaving(true);
      await patchWatchlistStock(settingItem.code, values);
      message.success("已保存");
      setSettingItem(null);
      loadData();
    } catch {
      // 校验失败或保存失败
    } finally {
      setSettingSaving(false);
    }
  };

  const columns = [
    {
      title: "代码",
      dataIndex: "code",
      key: "code",
      width: 100,
      render: (v: string, r: WatchlistStockItem) => (
        <a onClick={() => navigate(`/watchlist/stocks/${v}`)}>{v}</a>
      ),
    },
    {
      title: "名称",
      dataIndex: "name",
      key: "name",
      width: 100,
      render: (v: string, r: WatchlistStockItem) => <StockLink code={r.code} name={v}>{v}</StockLink>,
    },
    {
      title: "添加价",
      dataIndex: "add_price",
      key: "add_price",
      width: 90,
      render: (v: number | null) => fmtPrice(v),
    },
    {
      title: "添加日期",
      dataIndex: "add_date",
      key: "add_date",
      width: 110,
      render: (v: string | null) => v || "--",
    },
    {
      title: "当前价",
      dataIndex: "close",
      key: "close",
      width: 90,
      render: (v: number | null) => fmtPrice(v),
    },
    {
      title: "累计涨跌",
      key: "gain_since_add",
      width: 100,
      render: (_: unknown, r: WatchlistStockItem) => (
        <Text style={{ color: pctColor(r.gain_since_add_pct) }}>
          {fmtPct(r.gain_since_add_pct)}
        </Text>
      ),
    },
    {
      title: "今日涨跌",
      dataIndex: "change_pct",
      key: "change_pct",
      width: 90,
      render: (v: number | null) => (
        <Text style={{ color: pctColor(v) }}>{fmtPct(v)}</Text>
      ),
    },
    {
      title: "最新建议",
      key: "latest_action",
      width: 110,
      render: (_: unknown, r: WatchlistStockItem) => {
        const action = r.latest_action;
        if (!action) return <Text type="secondary">--</Text>;
        const cfg = actionConfig[action] || { color: "default", label: action };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: "建议买入区间",
      key: "latest_buy",
      width: 130,
      render: (_: unknown, r: WatchlistStockItem) => {
        if (r.latest_buy_low == null && r.latest_buy_high == null) return "--";
        return `${fmtPrice(r.latest_buy_low)} ~ ${fmtPrice(r.latest_buy_high)}`;
      },
    },
    {
      title: "置信度",
      dataIndex: "latest_confidence",
      key: "latest_confidence",
      width: 120,
      render: (v: number | null) => {
        if (v == null) return "--";
        const pct = Math.round((v || 0) * 100);
        return <Progress percent={pct} size="small" />;
      },
    },
    {
      title: "目标买入价",
      dataIndex: "target_buy_price",
      key: "target_buy_price",
      width: 100,
      render: (v: number | null) => fmtPrice(v),
    },
    {
      title: "操作",
      key: "actions",
      width: 130,
      render: (_: unknown, r: WatchlistStockItem) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/watchlist/stocks/${r.code}`)}>详情</Button>
          <Button size="small" onClick={() => openSetting(r)}>设置</Button>
          <Popconfirm title={`移除 ${r.name || r.code}？`} onConfirm={() => handleDelete(r.code)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const taskTotal = taskStatus?.total ?? 0;
  const taskDone = taskStatus?.done ?? 0;
  const taskPct = taskTotal > 0 ? Math.round((taskDone / taskTotal) * 100) : 0;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <StarOutlined style={{ marginRight: 8, color: "#faad14" }} />
          自选股追踪
        </Title>
        <Space>
          <Button icon={<SyncOutlined />} loading={snapshotLoading} onClick={handleSnapshot}>
            手动快照
          </Button>
          <Dropdown
            menu={{
              items: [
                { key: "morning", label: "早盘买点分析" },
                { key: "close", label: "收盘买点分析" },
              ],
              onClick: ({ key }) => handleAnalyze(key as "morning" | "close"),
            }}
          >
            <Button type="primary" icon={<BulbOutlined />} loading={analysisLoading}>
              <Space>
                生成分析
                <DownOutlined />
              </Space>
            </Button>
          </Dropdown>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            添加自选
          </Button>
        </Space>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />}

      {analysisLoading && taskStatus && (
        <Alert
          type="info"
          style={{ marginBottom: 16 }}
          message={`【${activePhase === "morning" ? "早盘" : "收盘"}分析进行中】已分析 ${taskDone}/${taskTotal} 只 (${taskPct}%)`}
          description={taskStatus.error ? `错误：${taskStatus.error}` : undefined}
        />
      )}

      <Spin spinning={loading}>
        {data && data.items.length === 0 ? (
          <Empty description="还没有自选股，点击右上角添加">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
              添加第一只
            </Button>
          </Empty>
        ) : (
          <Table
            rowKey="code"
            dataSource={data?.items || []}
            columns={columns}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            scroll={{ x: 1400 }}
            size="middle"
          />
        )}
      </Spin>

      {/* 添加 Modal */}
      <Modal
        title="添加自选股"
        open={addOpen}
        onCancel={() => {
          setAddOpen(false);
          setSearchKw("");
          setSearchResults([]);
        }}
        footer={null}
        width={560}
      >
        <Input
          placeholder="输入 6 位股票代码或名称（如 600519 / 茅台）"
          prefix={<SearchOutlined />}
          value={searchKw}
          onChange={(e) => onSearchChange(e.target.value)}
          allowClear
          onPressEnter={() => {
            if (searchKw.match(/^\d{6}$/)) handleAddByCode(searchKw.trim());
          }}
        />
        <div style={{ marginTop: 12, maxHeight: 360, overflowY: "auto" }}>
          {searching ? (
            <div style={{ textAlign: "center", padding: 24 }}>
              <Spin />
            </div>
          ) : searchResults && searchResults.length > 0 ? (
            <List
              size="small"
              dataSource={searchResults}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="add"
                      type="link"
                      icon={<PlusOutlined />}
                      onClick={() => handleAddFromResult(item)}
                    >
                      加入
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={`${item.name} (${item.code})`}
                    description={
                      <Space split={<span style={{ color: "#ccc" }}>|</span>}>
                        <span>当前价 {fmtPrice(item.price)}</span>
                        {item.change_pct != null && (
                          <span style={{ color: pctColor(item.change_pct) }}>
                            {fmtPct(item.change_pct)}
                          </span>
                        )}
                        {item.pe_ttm != null && <span>PE {item.pe_ttm.toFixed(1)}</span>}
                        {item.board && <span>{item.board}</span>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          ) : searchKw ? (
            <Empty description="无匹配，按回车直接添加此代码" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Text type="secondary">输入代码或名称开始搜索</Text>
          )}
        </div>
      </Modal>

      {/* 设置 Modal */}
      <Modal
        title={`设置 ${settingItem?.name || ""} (${settingItem?.code || ""})`}
        open={!!settingItem}
        onCancel={() => setSettingItem(null)}
        onOk={handleSettingSave}
        confirmLoading={settingSaving}
        okText="保存"
        cancelText="取消"
      >
        <Form form={settingForm} layout="vertical">
          <Form.Item name="target_buy_price" label="目标买入价">
            <InputNumber style={{ width: "100%" }} precision={2} placeholder="留空表示不设" />
          </Form.Item>
          <Form.Item name="stop_loss_price" label="止损价">
            <InputNumber style={{ width: "100%" }} precision={2} placeholder="留空表示不设" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { value: "watching", label: "关注中" },
                { value: "bought", label: "已买入" },
                { value: "dropped", label: "已放弃" },
              ]}
            />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
