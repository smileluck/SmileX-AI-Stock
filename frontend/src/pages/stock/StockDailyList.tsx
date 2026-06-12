import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Input,
  message,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { StarFilled, StarOutlined, SyncOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  addWatchlistStock,
  deleteWatchlistStock,
  fetchStockDailyList,
  fetchWatchlistStocks,
  triggerStockDailySnapshot,
} from "../../api/stock";
import StockLink from "../../components/StockLink";
import type { StockDailyItem, WatchlistStockItem } from "../../types";

const POSITIVE_COLOR = "#cf1322";
const NEGATIVE_COLOR = "#3f8600";
const PAGE_SIZE = 50;
const BOARD_OPTIONS = ["沪深主板", "创业板", "科创板", "北交所", "其他"];

function fmtNumber(v: number | null | undefined, digits = 2): string {
  return v == null ? "--" : v.toFixed(digits);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null) return "--";
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(2)}亿`;
  if (Math.abs(v) >= 1_0000) return `${(v / 1_0000).toFixed(2)}万`;
  return v.toLocaleString();
}

function valueColor(v: number | null | undefined): string | undefined {
  if (v == null || v === 0) return undefined;
  return v > 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;
}

export default function StockDailyList() {
  const [activeTab, setActiveTab] = useState("all");
  const [items, setItems] = useState<StockDailyItem[]>([]);
  const [watchItems, setWatchItems] = useState<WatchlistStockItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [board, setBoard] = useState<string | undefined>();
  const [keyword, setKeyword] = useState("");
  const [sortBy, setSortBy] = useState("change_pct");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const loadWatchlist = useCallback(async (tradeDate = date) => {
    const res = await fetchWatchlistStocks(tradeDate);
    setWatchItems(res.items);
  }, [date]);

  const loadAll = useCallback(async (targetPage = page, tradeDate = date) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchStockDailyList({
        tradeDate,
        sortBy,
        sortOrder,
        board,
        keyword: keyword || undefined,
        limit: PAGE_SIZE,
        offset: (targetPage - 1) * PAGE_SIZE,
        watchlistFirst: true,
      });
      setItems(res.items);
      setTotal(res.total);
      await loadWatchlist(tradeDate);
    } catch {
      setError("获取所有个股数据失败，请检查后端服务或先执行同步");
    } finally {
      setLoading(false);
    }
  }, [board, date, keyword, loadWatchlist, page, sortBy, sortOrder]);

  const loadCurrent = useCallback(async () => {
    if (activeTab === "watchlist") {
      setLoading(true);
      setError(null);
      try {
        await loadWatchlist(date);
      } catch {
        setError("获取自选股数据失败");
      } finally {
        setLoading(false);
      }
      return;
    }
    await loadAll(page, date);
  }, [activeTab, date, loadAll, loadWatchlist, page]);

  useEffect(() => {
    loadCurrent();
  }, [loadCurrent]);

  const toggleWatchlist = useCallback(async (record: StockDailyItem) => {
    try {
      if (record.is_watchlist) {
        await deleteWatchlistStock(record.code);
        message.success("已移出自选股");
      } else {
        await addWatchlistStock({ code: record.code, name: record.name });
        message.success("已加入自选股");
      }
      await loadCurrent();
    } catch {
      message.error("自选股操作失败");
    }
  }, [loadCurrent]);

  const handleSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      const res = await triggerStockDailySnapshot();
      if (res.success) {
        message.success(`同步完成：${res.item_count} 只`);
        await loadCurrent();
      } else {
        message.error(res.message || "同步失败");
      }
    } catch {
      message.error("触发同步失败");
    } finally {
      setSnapshotLoading(false);
    }
  };

  const columns: ColumnsType<StockDailyItem> = useMemo(() => [
    {
      title: "自选",
      key: "watchlist",
      width: 64,
      fixed: "left",
      render: (_, record) => (
        <Button
          type="text"
          size="small"
          icon={record.is_watchlist ? <StarFilled style={{ color: "#faad14" }} /> : <StarOutlined />}
          onClick={() => toggleWatchlist(record)}
        />
      ),
    },
    {
      title: "代码",
      dataIndex: "code",
      key: "code",
      width: 92,
      fixed: "left",
      render: (v: string, r) => <StockLink code={v} name={r.name}>{v}</StockLink>,
    },
    {
      title: "名称",
      dataIndex: "name",
      key: "name",
      width: 110,
      fixed: "left",
      render: (v: string, r) => (
        <Space size={4}>
          <span>{v || "--"}</span>
          {r.is_watchlist ? <Tag color="gold" style={{ margin: 0 }}>自选</Tag> : null}
        </Space>
      ),
    },
    { title: "板块", dataIndex: "board", key: "board", width: 90, render: (v: string) => v ? <Tag>{v}</Tag> : "--" },
    { title: "收盘价", dataIndex: "close", key: "close", width: 90, render: (v) => fmtNumber(v) },
    { title: "涨跌幅", dataIndex: "change_pct", key: "change_pct", width: 90, render: (v) => <span style={{ color: valueColor(v), fontWeight: 600 }}>{fmtPct(v)}</span> },
    { title: "涨跌额", dataIndex: "change", key: "change", width: 90, render: (v) => <span style={{ color: valueColor(v) }}>{fmtNumber(v)}</span> },
    { title: "成交额", dataIndex: "amount", key: "amount", width: 110, render: (v) => fmtAmount(v) },
    { title: "换手率", dataIndex: "turnover_rate", key: "turnover_rate", width: 90, render: (v) => fmtPct(v) },
    { title: "主力净流入", dataIndex: "main_net_inflow", key: "main_net_inflow", width: 120, render: (v) => <span style={{ color: valueColor(v) }}>{fmtAmount(v)}</span> },
    { title: "量比", dataIndex: "volume_ratio", key: "volume_ratio", width: 80, render: (v) => fmtNumber(v) },
    { title: "PE(TTM)", dataIndex: "pe_ttm", key: "pe_ttm", width: 90, render: (v) => fmtNumber(v) },
    { title: "PB", dataIndex: "pb", key: "pb", width: 80, render: (v) => fmtNumber(v) },
    { title: "总市值", dataIndex: "total_market_cap", key: "total_market_cap", width: 110, render: (v) => fmtAmount(v) },
  ], [toggleWatchlist]);

  const watchlistItems = watchItems.map((item) => ({ ...item, is_watchlist: true }));
  const currentItems = activeTab === "watchlist" ? watchlistItems : items;

  const handleTableChange = (pagination: TablePaginationConfig) => {
    const nextPage = pagination.current || 1;
    setPage(nextPage);
    loadAll(nextPage, date);
  };

  const resetToFirstPage = () => {
    setPage(1);
    loadAll(1, date);
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>所有个股</Typography.Title>
        <Space>
          <Button icon={<SyncOutlined spin={loading} />} onClick={loadCurrent} size="small">刷新</Button>
          <Button icon={<ThunderboltOutlined />} loading={snapshotLoading} onClick={handleSnapshot} size="small">同步</Button>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <DatePicker
            value={dayjs(date)}
            onChange={(d) => { const next = d?.format("YYYY-MM-DD") ?? dayjs().format("YYYY-MM-DD"); setDate(next); setPage(1); }}
            size="small"
          />
          <Select
            allowClear
            placeholder="板块"
            value={board}
            onChange={(v) => { setBoard(v); setPage(1); }}
            options={BOARD_OPTIONS.map((value) => ({ label: value, value }))}
            size="small"
            style={{ width: 120 }}
          />
          <Input.Search
            placeholder="代码或名称"
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={resetToFirstPage}
            size="small"
            style={{ width: 180 }}
          />
          <Select
            value={sortBy}
            onChange={(v) => { setSortBy(v); setPage(1); }}
            size="small"
            style={{ width: 130 }}
            options={[
              { label: "涨跌幅", value: "change_pct" },
              { label: "成交额", value: "amount" },
              { label: "换手率", value: "turnover_rate" },
              { label: "主力净流入", value: "main_net_inflow" },
              { label: "总市值", value: "total_market_cap" },
              { label: "量比", value: "volume_ratio" },
            ]}
          />
          <Select
            value={sortOrder}
            onChange={(v) => { setSortOrder(v); setPage(1); }}
            size="small"
            style={{ width: 100 }}
            options={[
              { label: "降序", value: "desc" },
              { label: "升序", value: "asc" },
            ]}
          />
          <Button size="small" type="primary" onClick={resetToFirstPage}>查询</Button>
        </Space>
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => { setActiveTab(key); setPage(1); }}
        items={[
          { key: "all", label: `全部个股 (${total})` },
          { key: "watchlist", label: `自选股 (${watchItems.length})` },
        ]}
      />

      <Spin spinning={loading}>
        <Table
          rowKey={(record) => `${record.code}-${record.trade_date || "watchlist"}`}
          dataSource={currentItems}
          columns={columns}
          size="small"
          scroll={{ x: 1300 }}
          onRow={(record) => ({
            style: record.is_watchlist ? { background: "#fffbe6" } : undefined,
          })}
          pagination={activeTab === "all" ? {
            current: page,
            pageSize: PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 只`,
          } : false}
          onChange={activeTab === "all" ? handleTableChange : undefined}
        />
      </Spin>
    </div>
  );
}
