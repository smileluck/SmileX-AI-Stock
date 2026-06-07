import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Switch,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Slider,
  Tabs,
  Typography,
  message,
  Tooltip,
  Alert,
  Spin,
} from "antd";
import {
  PlusOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import {
  fetchStrategies,
  createStrategy,
  updateStrategy,
  deleteStrategy,
  toggleStrategy,
  duplicateStrategy,
  testStrategy,
  fetchStrategyTypes,
} from "../api/strategy";
import type { StrategyItem, StrategyTypeInfo, WeightConfig } from "../api/strategy";

const { TextArea } = Input;
const { Text } = Typography;

const TYPE_COLORS: Record<string, string> = {
  stock_analysis: "blue",
  sector_analysis: "green",
  market_analysis: "orange",
  stock_review: "purple",
  stock_recommendation: "red",
};

const WEIGHT_LABELS: { key: keyof WeightConfig; label: string; color: string }[] = [
  { key: "fundamentals", label: "基本面", color: "#1890ff" },
  { key: "technicals", label: "技术面", color: "#52c41a" },
  { key: "news", label: "财经资讯", color: "#faad14" },
  { key: "capital_flow", label: "资金流入", color: "#722ed1" },
  { key: "sentiment", label: "消息面", color: "#eb2f96" },
];

const DEFAULT_WEIGHTS: WeightConfig = {
  fundamentals: 30,
  technicals: 25,
  news: 20,
  capital_flow: 15,
  sentiment: 10,
};

export default function StrategyPage() {
  const [items, setItems] = useState<StrategyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [types, setTypes] = useState<StrategyTypeInfo[]>([]);
  const [activeTab, setActiveTab] = useState("all");

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<StrategyItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // Test state
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [testingItem, setTestingItem] = useState<StrategyItem | null>(null);
  const [testInput, setTestInput] = useState("");
  const [testResult, setTestResult] = useState("");
  const [testLoading, setTestLoading] = useState(false);

  const loadTypes = useCallback(async () => {
    try {
      const data = await fetchStrategyTypes();
      setTypes(data);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const type = activeTab === "all" ? undefined : activeTab;
      const res = await fetchStrategies(type);
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载策略列表失败");
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { loadTypes(); }, [loadTypes]);
  useEffect(() => { loadData(); }, [loadData]);

  const handleToggle = async (id: number) => {
    try {
      await toggleStrategy(id);
      loadData();
    } catch {
      message.error("切换状态失败");
    }
  };

  const handleDuplicate = async (id: number) => {
    try {
      await duplicateStrategy(id);
      message.success("复制成功");
      loadData();
    } catch {
      message.error("复制失败");
    }
  };

  const handleDelete = async (item: StrategyItem) => {
    if (item.is_default) {
      message.warning("默认策略不可删除，可以禁用");
      return;
    }
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除策略「${item.name}」吗？`,
      okType: "danger",
      onOk: async () => {
        try {
          await deleteStrategy(item.id);
          message.success("删除成功");
          loadData();
        } catch (e: unknown) {
          const err = e as { response?: { data?: { detail?: string } } };
          message.error(err.response?.data?.detail || "删除失败");
        }
      },
    });
  };

  const openCreateModal = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({
      type: "stock_analysis",
      weight_config: { ...DEFAULT_WEIGHTS },
      news_enabled: true,
      news_count: 15,
      is_enabled: true,
    });
    setModalOpen(true);
  };

  const openEditModal = (item: StrategyItem) => {
    setEditingItem(item);
    form.setFieldsValue({
      name: item.name,
      type: item.type,
      description: item.description,
      prompt_template: item.prompt_template,
      weight_config: item.weight_config,
      news_enabled: item.news_enabled,
      news_count: item.news_count,
      is_enabled: item.is_enabled,
      model_override: item.model_override,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingItem) {
        await updateStrategy(editingItem.id, values);
        message.success("更新成功");
      } else {
        await createStrategy(values);
        message.success("创建成功");
      }
      setModalOpen(false);
      loadData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testingItem) return;
    setTestLoading(true);
    setTestResult("");
    try {
      const res = await testStrategy(testingItem.id, testInput);
      setTestResult(res.result);
    } catch {
      setTestResult("测试失败，请检查LLM配置");
    } finally {
      setTestLoading(false);
    }
  };

  const tabItems = [
    { key: "all", label: "全部" },
    ...types.map((t) => ({ key: t.key, label: t.label })),
  ];

  const columns = [
    {
      title: "策略名称",
      dataIndex: "name",
      key: "name",
      width: 200,
      render: (name: string, record: StrategyItem) => (
        <Space>
          <span style={{ fontWeight: 500 }}>{name}</span>
          {record.is_default && <Tag color="gold">默认</Tag>}
        </Space>
      ),
    },
    {
      title: "类型",
      dataIndex: "type",
      key: "type",
      width: 130,
      render: (type: string) => {
        const info = types.find((t) => t.key === type);
        return <Tag color={TYPE_COLORS[type]}>{info?.label || type}</Tag>;
      },
    },
    {
      title: "说明",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
    },
    {
      title: "状态",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 90,
      render: (v: boolean, record: StrategyItem) => (
        <Switch
          checked={v}
          onChange={() => handleToggle(record.id)}
          checkedChildren={<CheckCircleOutlined />}
          unCheckedChildren={<CloseCircleOutlined />}
        />
      ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => v?.slice(0, 16) || "-",
    },
    {
      title: "操作",
      key: "actions",
      width: 180,
      render: (_: unknown, record: StrategyItem) => (
        <Space size={4}>
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEditModal(record)} />
          </Tooltip>
          <Tooltip title="复制">
            <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => handleDuplicate(record.id)} />
          </Tooltip>
          <Tooltip title="测试">
            <Button type="text" size="small" icon={<ExperimentOutlined />} onClick={() => { setTestingItem(record); setTestInput(""); setTestResult(""); setTestModalOpen(true); }} />
          </Tooltip>
          <Tooltip title={record.is_default ? "默认策略不可删除" : "删除"}>
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={record.is_default}
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="策略管理"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新建策略
          </Button>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          style={{ marginBottom: 16 }}
        />
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
          size="middle"
        />
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        title={editingItem ? "编辑策略" : "新建策略"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={780}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="策略名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="如：综合个股分析" />
          </Form.Item>

          <Form.Item name="type" label="策略类型" rules={[{ required: true }]}>
            <Select>
              {types.map((t) => (
                <Select.Option key={t.key} value={t.key}>
                  {t.label} — {t.description}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="description" label="策略说明">
            <Input placeholder="简要描述策略用途" />
          </Form.Item>

          <Form.Item name="prompt_template" label="提示词模板" rules={[{ required: true, message: "请输入提示词" }]}>
            <TextArea
              rows={10}
              placeholder="输入分析提示词模板..."
              style={{ fontFamily: "monospace", fontSize: 13 }}
            />
          </Form.Item>

          {/* Weight Config */}
          <Card size="small" title="权重配置 (%)" style={{ marginBottom: 16 }}>
            <WeightSliders form={form} />
          </Card>

          <Space style={{ marginBottom: 16 }}>
            <Form.Item name="news_enabled" label="包含财经资讯" valuePropName="checked" noStyle>
              <Switch />
            </Form.Item>
            <Form.Item name="news_count" label="资讯条数" noStyle>
              <InputNumber min={1} max={50} style={{ width: 80 }} />
            </Form.Item>
            <Form.Item name="is_enabled" label="启用" valuePropName="checked" noStyle>
              <Switch />
            </Form.Item>
          </Space>

          <Form.Item name="model_override" label="模型覆盖（可选）">
            <Input placeholder="留空使用默认分析模型" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Test Modal */}
      <Modal
        title={
          <Space>
            <ThunderboltOutlined />
            <span>测试策略：{testingItem?.name}</span>
          </Space>
        }
        open={testModalOpen}
        onCancel={() => setTestModalOpen(false)}
        footer={null}
        width={720}
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">输入测试数据（留空使用默认提示）</Text>
          <TextArea
            rows={4}
            value={testInput}
            onChange={(e) => setTestInput(e.target.value)}
            placeholder="可选：输入测试数据..."
            style={{ marginTop: 4 }}
          />
        </div>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={testLoading}
          onClick={handleTest}
          style={{ marginBottom: 12 }}
        >
          运行测试
        </Button>
        {testResult && (
          <Card size="small" title="测试结果" style={{ marginTop: 8 }}>
            <Spin spinning={testLoading}>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, maxHeight: 400, overflow: "auto" }}>
                {testResult}
              </pre>
            </Spin>
          </Card>
        )}
      </Modal>
    </div>
  );
}

function WeightSliders({ form }: { form: Form.Instance }) {
  const weights = Form.useWatch("weight_config", form) || DEFAULT_WEIGHTS;
  const total = WEIGHT_LABELS.reduce((s, w) => s + (weights[w.key] || 0), 0);
  const valid = Math.abs(total - 100) < 0.01;

  return (
    <div>
      {!valid && (
        <Alert
          message={`权重总和为 ${total}%，需调整为 100%`}
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}
      {WEIGHT_LABELS.map(({ key, label, color }) => (
        <div key={key} style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
          <span style={{ width: 70, color, fontWeight: 500 }}>{label}</span>
          <Slider
            min={0}
            max={100}
            value={weights[key] || 0}
            onChange={(v) => {
              const current = form.getFieldValue("weight_config") || { ...DEFAULT_WEIGHTS };
              form.setFieldsValue({ weight_config: { ...current, [key]: v } });
            }}
            style={{ flex: 1, margin: "0 12px" }}
          />
          <span style={{ width: 40, textAlign: "right" }}>{weights[key] || 0}%</span>
        </div>
      ))}
      <div style={{ textAlign: "right", marginTop: 4 }}>
        <Text strong type={valid ? "success" : "danger"}>
          合计：{total}%
        </Text>
      </div>
    </div>
  );
}
