import { useState, useEffect, useCallback } from "react";
import { Card, Typography, Tag, List, Button, Space, Spin, message } from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  ApiOutlined,
} from "@ant-design/icons";
import { fetchProxyStatus, testProxyConnection } from "../api/aiConfig";
import type { ProxyStatus } from "../api/aiConfig";

export default function LLMConfig() {
  const [status, setStatus] = useState<ProxyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);

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

  useEffect(() => {
    load();
  }, [load]);

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

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          LLM 配置
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
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
    </div>
  );
}
