import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Typography,
  Tag,
  List,
  Button,
  Space,
  Spin,
  message,
  Select,
  Table,
  Alert,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  ApiOutlined,
  SaveOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import {
  fetchProxyStatus,
  testProxyConnection,
  fetchModelConfigs,
  updateModelConfigs,
  fetchAvailableModels,
} from "../api/aiConfig";
import type { ProxyStatus, ModelConfigItem } from "../api/aiConfig";

export default function LLMConfig() {
  const [status, setStatus] = useState<ProxyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  const [configs, setConfigs] = useState<ModelConfigItem[]>([]);
  const [localConfigs, setLocalConfigs] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [configsLoading, setConfigsLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchProxyStatus();
      setStatus(result);
    } catch {
      setStatus({ success: false, error: "无法连接后端服务" });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadConfigs = useCallback(async () => {
    setConfigsLoading(true);
    try {
      const [configList, models] = await Promise.all([
        fetchModelConfigs(),
        fetchAvailableModels(),
      ]);
      setConfigs(configList);
      setAvailableModels(models);
      setLocalConfigs({});
    } catch {
      message.error("加载模型配置失败");
    } finally {
      setConfigsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    loadConfigs();
  }, [load, loadConfigs]);

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await testProxyConnection();
      setStatus(result);
      if (result.success) {
        message.success("LiteLLM Proxy 连接正常");
      } else {
        message.error(`连接失败: ${result.error}`);
      }
    } catch {
      message.error("测试请求失败");
    } finally {
      setTesting(false);
    }
  };

  const hasChanges = Object.keys(localConfigs).length > 0;

  const handleSave = async () => {
    const updates = Object.entries(localConfigs).map(([key, model]) => ({
      function_key: key,
      model_name: model,
    }));
    setSaving(true);
    try {
      await updateModelConfigs(updates);
      message.success("模型配置已保存，立即生效");
      await loadConfigs();
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      title: "AI 功能",
      dataIndex: "label",
      key: "label",
      width: 140,
      render: (label: string, record: ModelConfigItem) => (
        <div>
          <div style={{ fontWeight: 500 }}>{label}</div>
          <div style={{ fontSize: 12, color: "#999" }}>{record.description}</div>
        </div>
      ),
    },
    {
      title: "使用模型",
      dataIndex: "model_name",
      key: "model_name",
      width: 220,
      render: (model: string, record: ModelConfigItem) => (
        <Select
          value={localConfigs[record.function_key] ?? model}
          onChange={(val) =>
            setLocalConfigs((prev) => ({ ...prev, [record.function_key]: val }))
          }
          style={{ width: "100%" }}
          options={availableModels.map((m) => ({ label: m, value: m }))}
          placeholder="选择模型"
          disabled={availableModels.length === 0}
        />
      ),
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      width: 100,
      render: (source: string, record: ModelConfigItem) => {
        const changed = record.function_key in localConfigs;
        if (changed) return <Tag color="orange">待保存</Tag>;
        return source === "database" ? (
          <Tag color="blue">数据库</Tag>
        ) : (
          <Tag>默认</Tag>
        );
      },
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          LLM 配置
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { load(); loadConfigs(); }} loading={loading}>
            刷新
          </Button>
          <Button icon={<ApiOutlined />} onClick={handleTest} loading={testing}>
            测试连接
          </Button>
        </Space>
      </Space>

      <Card title="LiteLLM Proxy" size="small" style={{ marginBottom: 16 }}>
        {loading && !status ? (
          <Spin />
        ) : status?.success ? (
          <>
            <Space style={{ marginBottom: 12 }}>
              <Tag icon={<CheckCircleOutlined />} color="success">已连接</Tag>
            </Space>
            <Typography.Text type="secondary">可用模型：</Typography.Text>
            <List
              size="small"
              dataSource={status.models || []}
              renderItem={(model) => (
                <List.Item>
                  <Typography.Text code>{model}</Typography.Text>
                </List.Item>
              )}
              locale={{ emptyText: "暂无模型" }}
            />
          </>
        ) : (
          <Space>
            <Tag icon={<CloseCircleOutlined />} color="error">未连接</Tag>
            <Typography.Text type="danger">
              {status?.error || "未知错误"}
            </Typography.Text>
          </Space>
        )}
      </Card>

      <Card
        title={
          <Space>
            <SettingOutlined />
            <span>模型分配</span>
          </Space>
        }
        size="small"
        extra={
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={saving}
            disabled={!hasChanges}
          >
            保存配置
          </Button>
        }
      >
        {configsLoading ? (
          <Spin />
        ) : (
          <>
            {availableModels.length === 0 && (
              <Alert
                message="Proxy 未连接，无法获取可用模型列表"
                description="请确保 LiteLLM Proxy 正在运行后再配置模型"
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}
            <Table
              columns={columns}
              dataSource={configs}
              rowKey="function_key"
              size="small"
              pagination={false}
            />
          </>
        )}
      </Card>
    </div>
  );
}
