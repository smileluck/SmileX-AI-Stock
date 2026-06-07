import { useState, useEffect, useCallback } from "react";
import {
  Typography, Card, Table, Tag, Button, Spin, Alert, DatePicker, Space, message,
} from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  fetchLatestSectorAnalysis,
  fetchSectorAnalysisHistory,
  triggerSectorAnalysis,
} from "../api/sectorAnalysis";
import { fetchActiveStrategy } from "../api/strategy";
import type { StrategyItem } from "../api/strategy";
import type { SectorAnalysisItem } from "../types";

function SectorAnalysisTab() {
  const [latest, setLatest] = useState<SectorAnalysisItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<SectorAnalysisItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [activeStrategy, setActiveStrategy] = useState<StrategyItem | null>(null);
  const pageSize = 10;

  const loadLatest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLatestSectorAnalysis();
      setLatest(res);
    } catch {
      setError("获取板块分析数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchSectorAnalysisHistory(pageSize, (page - 1) * pageSize);
      setHistoryItems(res.items);
      setHistoryTotal(res.total);
    } catch {
      // silently ignore
    }
  }, [page]);

  useEffect(() => { loadLatest(); }, [loadLatest]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => {
    fetchActiveStrategy("sector_analysis").then(setActiveStrategy).catch(() => {});
  }, []);

  const handleGenerate = async (date?: string) => {
    setGenerating(true);
    try {
      const res = await triggerSectorAnalysis(date);
      if (res.success) {
        message.success(res.message);
        setLatest(res.data);
        loadHistory();
      } else {
        message.error(res.message);
      }
    } catch {
      message.error("生成失败，请检查后端服务");
    } finally {
      setGenerating(false);
    }
  };

  const historyColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    {
      title: "状态", dataIndex: "status", key: "status",
      render: (s: string) => s === "completed" ? <Tag color="green">已完成</Tag> : <Tag color="default">{s}</Tag>,
    },
    { title: "模型", dataIndex: "model_used", key: "model" },
    { title: "生成时间", dataIndex: "created_at", key: "created_at" },
  ];

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <DatePicker
            onChange={(d) => { if (d) handleGenerate(d.format("YYYY-MM-DD")); }}
            placeholder="选择日期手动生成"
          />
          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={() => handleGenerate()}>
            生成板块分析
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}

      <Spin spinning={loading}>
        {latest && (
          <Card title={`📊 ${latest.trade_date} 板块AI分析`} style={{ marginBottom: 16 }}>
            <Typography.Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8 }}>
              {latest.analysis_text || "暂无分析内容"}
            </Typography.Paragraph>
          </Card>
        )}
        {!latest && !loading && (
          <Card><Typography.Text type="secondary">暂无板块分析数据，点击"生成板块分析"开始</Typography.Text></Card>
        )}
      </Spin>

      <Card title="历史分析" style={{ marginTop: 16 }}>
        <Table
          size="small"
          dataSource={historyItems}
          columns={historyColumns}
          rowKey="id"
          pagination={{ current: page, pageSize, total: historyTotal, onChange: setPage, showTotal: (t) => `共 ${t} 条` }}
          onRow={(r) => ({ onClick: () => setLatest(r), style: { cursor: "pointer" } })}
        />
      </Card>
    </>
  );
}

export default function SectorAnalysis() {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>板块AI分析</Typography.Title>
        {activeStrategy && (
          <Space>
            <Tag color="green">当前策略：{activeStrategy.name}</Tag>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              自动分析：工作日 16:00 / 周日 21:00
            </Typography.Text>
          </Space>
        )}
      </div>
      <SectorAnalysisTab />
    </div>
  );
}
