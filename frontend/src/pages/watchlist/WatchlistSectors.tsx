import { useState, useEffect, useCallback } from "react";
import {
  Tabs,
  Card,
  Button,
  List,
  Tag,
  Empty,
  Input,
  Space,
  Modal,
  Form,
  Popconfirm,
  message,
  Spin,
  Typography,
  Select,
  Drawer,
  Row,
  Col,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import {
  fetchMarketSectors,
  addMarketSector,
  deleteMarketSector,
  fetchCustomSectors,
  createCustomSector,
  deleteCustomSector,
  fetchCustomSectorStocks,
  addCustomSectorStock,
  removeCustomSectorStock,
  searchWatchlistStock,
} from "../../api/watchlist";
import type {
  WatchlistSectorItem,
  WatchlistCustomSectorItem,
  WatchlistCustomSectorStockItem,
  WatchlistSearchItem,
} from "../../types";

const { Title } = Typography;

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "--";
  return v.toFixed(2);
}

export default function WatchlistSectors() {
  const [marketSectors, setMarketSectors] = useState<WatchlistSectorItem[]>([]);
  const [customSectors, setCustomSectors] = useState<WatchlistCustomSectorItem[]>([]);
  const [loading, setLoading] = useState(false);

  const [marketForm] = Form.useForm();
  const [customForm] = Form.useForm();
  const [marketOpen, setMarketOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);

  // 成分股管理 Drawer
  const [drawerSector, setDrawerSector] = useState<WatchlistCustomSectorItem | null>(null);
  const [sectorStocks, setSectorStocks] = useState<WatchlistCustomSectorStockItem[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [searchKw, setSearchKw] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<WatchlistSearchItem[] | undefined>(undefined);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [ms, cs] = await Promise.all([fetchMarketSectors(), fetchCustomSectors()]);
      setMarketSectors(ms);
      setCustomSectors(cs);
    } catch {
      message.error("加载板块失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddMarket = async () => {
    const values = await marketForm.validateFields();
    try {
      await addMarketSector(values);
      message.success("已关注板块");
      marketForm.resetFields();
      setMarketOpen(false);
      loadData();
    } catch {
      message.error("关注失败");
    }
  };

  const handleAddCustom = async () => {
    const values = await customForm.validateFields();
    try {
      await createCustomSector(values);
      message.success("已创建自定义板块");
      customForm.resetFields();
      setCustomOpen(false);
      loadData();
    } catch {
      message.error("创建失败");
    }
  };

  // Drawer 操作
  const openDrawer = async (sector: WatchlistCustomSectorItem) => {
    setDrawerSector(sector);
    setSearchKw("");
    setSearchResults(undefined);
    setDrawerLoading(true);
    try {
      const stocks = await fetchCustomSectorStocks(sector.id);
      setSectorStocks(stocks);
    } catch {
      message.error("加载成分股失败");
    } finally {
      setDrawerLoading(false);
    }
  };

  const doSearch = (kw: string, sectorId: number) => {
    if (!kw.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    searchWatchlistStock(kw.trim())
      .then((res) => setSearchResults(res))
      .catch(() => setSearchResults([]))
      .finally(() => setSearching(false));
  };

  const onSearchChange = (v: string) => {
    setSearchKw(v);
    doSearch(v, drawerSector?.id ?? 0);
  };

  const handleAddStock = async (item: WatchlistSearchItem) => {
    if (!drawerSector) return;
    try {
      await addCustomSectorStock(drawerSector.id, { code: item.code, name: item.name });
      message.success(`已加入 ${item.name || item.code}`);
      const stocks = await fetchCustomSectorStocks(drawerSector.id);
      setSectorStocks(stocks);
      loadData();
    } catch {
      message.error("加入失败");
    }
  };

  const handleRemoveStock = async (code: string) => {
    if (!drawerSector) return;
    try {
      await removeCustomSectorStock(drawerSector.id, code);
      message.success("已移除");
      const stocks = await fetchCustomSectorStocks(drawerSector.id);
      setSectorStocks(stocks);
      loadData();
    } catch {
      message.error("移除失败");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>自选板块</Title>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </div>

      <Spin spinning={loading}>
        <Tabs
          items={[
            {
              key: "market",
              label: `市场板块关注 (${marketSectors.length})`,
              children: (
                <Card
                  size="small"
                  extra={
                    <Button icon={<PlusOutlined />} onClick={() => setMarketOpen(true)}>关注新板块</Button>
                  }
                  title="已关注的市场板块"
                >
                  {marketSectors.length === 0 ? (
                    <Empty description="还没有关注任何市场板块" />
                  ) : (
                    <List
                      dataSource={marketSectors}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Popconfirm
                              key="del"
                              title="取消关注？"
                              onConfirm={async () => {
                                await deleteMarketSector(item.id);
                                message.success("已取消关注");
                                loadData();
                              }}
                            >
                              <Button danger icon={<DeleteOutlined />} size="small">取消关注</Button>
                            </Popconfirm>,
                          ]}
                        >
                          <List.Item.Meta
                            title={
                              <Space>
                                {item.sector_name}
                                <Tag color={item.sector_type === "industry" ? "blue" : "purple"}>
                                  {item.sector_type === "industry" ? "行业" : "概念"}
                                </Tag>
                              </Space>
                            }
                            description={item.note || "无备注"}
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              ),
            },
            {
              key: "custom",
              label: `自定义板块 (${customSectors.length})`,
              children: (
                <Card
                  size="small"
                  extra={
                    <Button icon={<PlusOutlined />} onClick={() => setCustomOpen(true)}>创建板块</Button>
                  }
                  title="我的自定义板块组合"
                >
                  {customSectors.length === 0 ? (
                    <Empty description="还没有自定义板块，点击右上角创建" />
                  ) : (
                    <List
                      dataSource={customSectors}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Button
                              key="manage"
                              icon={<SettingOutlined />}
                              size="small"
                              onClick={() => openDrawer(item)}
                            >
                              管理成分股
                            </Button>,
                            <Popconfirm
                              key="del"
                              title={`删除「${item.name}」？（成分股关联会被解除）`}
                              onConfirm={async () => {
                                await deleteCustomSector(item.id);
                                message.success("已删除");
                                loadData();
                              }}
                            >
                              <Button danger icon={<DeleteOutlined />} size="small">删除</Button>
                            </Popconfirm>,
                          ]}
                        >
                          <List.Item.Meta
                            title={
                              <Space>
                                {item.name}
                                <Tag color="cyan">{item.stock_count || 0} 只成分股</Tag>
                              </Space>
                            }
                            description={item.note || "无备注"}
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              ),
            },
          ]}
        />
      </Spin>

      <Modal
        title="关注市场板块"
        open={marketOpen}
        onCancel={() => setMarketOpen(false)}
        onOk={handleAddMarket}
        okText="关注"
        cancelText="取消"
      >
        <Form form={marketForm} layout="vertical">
          <Form.Item name="sector_name" label="板块名称" rules={[{ required: true, message: "请输入板块名" }]}>
            <Input placeholder="如 半导体 / AI / 新能源" />
          </Form.Item>
          <Form.Item name="sector_type" label="板块类型" initialValue="industry">
            <Select
              options={[
                { value: "industry", label: "行业" },
                { value: "concept", label: "概念" },
              ]}
            />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="创建自定义板块"
        open={customOpen}
        onCancel={() => setCustomOpen(false)}
        onOk={handleAddCustom}
        okText="创建"
        cancelText="取消"
      >
        <Form form={customForm} layout="vertical">
          <Form.Item name="name" label="板块名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="如 我的科技股 / 长线持仓" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={drawerSector ? `管理成分股：${drawerSector.name}` : ""}
        open={!!drawerSector}
        onClose={() => setDrawerSector(null)}
        width={680}
      >
        <Spin spinning={drawerLoading}>
          <Row gutter={16}>
            <Col span={12}>
              <Card title="搜索添加" size="small">
                <Input
                  placeholder="代码或名称"
                  prefix={<SearchOutlined />}
                  value={searchKw}
                  onChange={(e) => onSearchChange(e.target.value)}
                  allowClear
                />
                <div style={{ marginTop: 8, maxHeight: 360, overflowY: "auto" }}>
                  {searching ? (
                    <div style={{ textAlign: "center", padding: 16 }}><Spin /></div>
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
                              onClick={() => handleAddStock(item)}
                            >
                              加入
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={`${item.name} (${item.code})`}
                            description={`当前价 ${fmtPrice(item.price)}`}
                          />
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={searchKw ? "无匹配" : "输入开始搜索"} />
                  )}
                </div>
              </Card>
            </Col>
            <Col span={12}>
              <Card title={`已加入成分股 (${sectorStocks.length})`} size="small">
                <div style={{ maxHeight: 420, overflowY: "auto" }}>
                  {sectorStocks.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有成分股" />
                  ) : (
                    <List
                      size="small"
                      dataSource={sectorStocks}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Popconfirm
                              key="rm"
                              title="移除？"
                              onConfirm={() => handleRemoveStock(item.code)}
                            >
                              <Button danger size="small" icon={<DeleteOutlined />} />
                            </Popconfirm>,
                          ]}
                        >
                          <List.Item.Meta
                            title={`${item.name} (${item.code})`}
                            description={`添加价 ${fmtPrice(item.add_price)} / 当前 ${fmtPrice(item.close)}`}
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </div>
              </Card>
            </Col>
          </Row>
        </Spin>
      </Drawer>
    </div>
  );
}
