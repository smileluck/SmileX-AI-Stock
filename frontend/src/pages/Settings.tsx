import { useState, useEffect, useCallback } from "react";
import {
  Table, Tag, Card, Typography, message, Button, Space, Modal, Form, Input, InputNumber,
  Select, Popconfirm, Alert, Slider,
} from "antd";
import {
  PlusOutlined, ReloadOutlined, ApiOutlined, EditOutlined, DeleteOutlined,
  StarOutlined, StarFilled, CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import {
  fetchProviders, fetchAIConfigs, createAIConfig, updateAIConfig, deleteAIConfig, testAIConnection,
} from "../api/aiConfig";
import type { AIModelConfig, AIModelConfigCreate, AIModelConfigUpdate, ProviderInfo } from "../types";
import { PROVIDER_COLOR_MAP } from "../types";

interface FormValues {
  name: string;
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  temperature: number;
  max_tokens: number;
  is_default: boolean;
}

export default function Settings() {
  const [configs, setConfigs] = useState<AIModelConfig[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AIModelConfig | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [form] = Form.useForm<FormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([fetchProviders(), fetchAIConfigs()]);
      setProviders(p);
      setConfigs(c);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectedProvider = Form.useWatch("provider", form);
  const providerDefaultUrl = providers.find((p) => p.id === selectedProvider)?.base_url || "";

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ temperature: 0.7, max_tokens: 4096, is_default: configs.length === 0 });
    setModalOpen(true);
  };

  const openEdit = (record: AIModelConfig) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      provider: record.provider,
      model: record.model,
      base_url: record.base_url,
      api_key: "",
      temperature: record.temperature,
      max_tokens: record.max_tokens,
      is_default: record.is_default,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        const update: AIModelConfigUpdate = { ...values };
        if (!values.api_key) delete update.api_key;
        await updateAIConfig(editing.id, update);
        message.success("更新成功");
      } else {
        await createAIConfig(values as AIModelConfigCreate);
        message.success("添加成功");
      }
      setModalOpen(false);
      await load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "操作失败";
      message.error(msg);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAIConfig(id);
      message.success("已删除");
      await load();
    } catch {
      message.error("删除失败");
    }
  };

  const handleSetDefault = async (id: number) => {
    try {
      await updateAIConfig(id, { is_default: true });
      message.success("已设为默认");
      await load();
    } catch {
      message.error("操作失败");
    }
  };

  const handleToggleEnabled = async (record: AIModelConfig) => {
    try {
      await updateAIConfig(record.id, { is_enabled: !record.is_enabled });
      message.success(record.is_enabled ? "已禁用" : "已启用");
      await load();
    } catch {
      message.error("操作失败");
    }
  };

  const handleTest = async (record: AIModelConfig) => {
    setTesting(record.id);
    try {
      const result = await testAIConnection(record.id);
      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch {
      message.error("测试请求失败");
    } finally {
      setTesting(null);
    }
  };

  const handleTestInModal = async () => {
    try {
      const values = await form.validateFields();
      const result = await testAIConnection(values as AIModelConfigCreate);
      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch {
      message.error("请先填写完整配置");
    }
  };

  const columns = [
    {
      title: "名称",
      dataIndex: "name",
      width: 180,
    },
    {
      title: "产商",
      dataIndex: "provider",
      width: 120,
      render: (v: string) => (
        <Tag color={PROVIDER_COLOR_MAP[v] || "default"}>{providers.find((p) => p.id === v)?.label || v}</Tag>
      ),
    },
    {
      title: "模型",
      dataIndex: "model",
      width: 200,
    },
    {
      title: "API Key",
      dataIndex: "api_key_masked",
      width: 120,
      render: (v: string) => <Typography.Text code>{v}</Typography.Text>,
    },
    {
      title: "状态",
      width: 80,
      render: (_: unknown, record: AIModelConfig) =>
        record.is_enabled ? (
          <Tag icon={<CheckCircleOutlined />} color="success">启用</Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="default">禁用</Tag>
        ),
    },
    {
      title: "默认",
      dataIndex: "is_default",
      width: 60,
      render: (v: boolean) => v ? <StarFilled style={{ color: "#faad14", fontSize: 16 }} /> : <StarOutlined style={{ color: "#d9d9d9" }} />,
    },
    {
      title: "操作",
      width: 260,
      render: (_: unknown, record: AIModelConfig) => (
        <Space size={4}>
          <Button size="small" icon={<ApiOutlined />} loading={testing === record.id} onClick={() => handleTest(record)}>
            测试
          </Button>
          {!record.is_default && (
            <Button size="small" icon={<StarOutlined />} onClick={() => handleSetDefault(record.id)}>
              设为默认
            </Button>
          )}
          <Button size="small" onClick={() => handleToggleEnabled(record)}>
            {record.is_enabled ? "禁用" : "启用"}
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          AI 模型配置
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加模型</Button>
        </Space>
      </Space>

      {configs.length === 0 && !loading && (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message="尚未配置 AI 模型"
          description="点击「添加模型」配置你的第一个 LLM 模型。请确保后端 .env 中已设置 ENCRYPTION_KEY。"
        />
      )}

      <Card size="small">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={configs}
          size="small"
          loading={loading}
          pagination={false}
        />
      </Card>

      <Modal
        title={editing ? "编辑模型" : "添加模型"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={560}
        okText={editing ? "保存" : "添加"}
        footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            <CancelBtn />
            <Button onClick={handleTestInModal} icon={<ApiOutlined />}>测试连接</Button>
            <OkBtn />
          </Space>
        )}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="provider" label="产商" rules={[{ required: true, message: "请选择产商" }]}>
            <Select
              placeholder="选择产商"
              options={providers.map((p) => ({ value: p.id, label: p.label }))}
              onChange={(v: string) => {
                const p = providers.find((x) => x.id === v);
                if (p?.base_url) form.setFieldsValue({ base_url: p.base_url });
              }}
            />
          </Form.Item>
          <Form.Item name="model" label="模型" rules={[{ required: true, message: "请输入模型名称" }]}>
            <Input placeholder="如 deepseek-chat, claude-sonnet-4-20250514" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="显示名称" />
          </Form.Item>
          <Form.Item name="base_url" label="API Base URL">
            <Input placeholder={providerDefaultUrl || "留空使用产商默认地址"} />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={editing ? [] : [{ required: true, message: "请输入 API Key" }]}
          >
            <Input.Password placeholder={editing ? "留空保持原密钥不变" : "输入 API Key"} />
          </Form.Item>
          <Form.Item name="temperature" label="Temperature">
            <Slider min={0} max={2} step={0.1} />
          </Form.Item>
          <Form.Item name="max_tokens" label="Max Tokens">
            <InputNumber min={1} max={128000} step={256} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="is_default" valuePropName="checked">
            <Input type="hidden" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
