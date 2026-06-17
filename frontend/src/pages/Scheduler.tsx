import { useState, useCallback } from "react";
import { Table, Tag, Descriptions, Card, Typography, message, Button, Space } from "antd";
import { SyncOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { fetchSchedule, fetchSyncLogs, triggerSync } from "../api/news";
import { usePolling } from "../hooks/usePolling";
import type { ScheduleJob, SyncLogItem } from "../types";

export default function SchedulerPage() {
  const [jobs, setJobs] = useState<ScheduleJob[]>([]);
  const [logs, setLogs] = useState<SyncLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [schedule, logData] = await Promise.all([fetchSchedule(), fetchSyncLogs(100)]);
      setJobs(schedule.jobs);
      setLogs(logData.items);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(load, 60_000);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await triggerSync();
      message.success(`同步完成，共抓取 ${result.total} 条`);
      await load();
    } catch {
      message.error("同步失败");
    } finally {
      setSyncing(false);
    }
  };

  const logColumns = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 180,
      render: (v: string) => dayjs(v).format("YYYY-MM-DD HH:mm:ss"),
    },
    {
      title: "触发方式",
      dataIndex: "trigger",
      width: 100,
      render: (v: string) => (
        <Tag color={v === "manual" ? "blue" : "green"}>{v === "manual" ? "手动" : "定时"}</Tag>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v: string) => <Tag color={v === "ok" ? "success" : "error"}>{v === "ok" ? "成功" : "异常"}</Tag>,
    },
    {
      title: "抓取数",
      dataIndex: "total",
      width: 80,
    },
    {
      title: "耗时",
      dataIndex: "duration",
      width: 90,
      render: (v: number) => `${v}s`,
    },
    {
      title: "各源详情",
      dataIndex: "results",
      render: (results: SyncLogItem["results"]) => (
        <Space size={[4, 4]} wrap>
          {results.map((r) => (
            <Tag key={r.source} color={r.status === "ok" ? "default" : "error"}>
              {r.label}: {r.count}
            </Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          定时任务
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<SyncOutlined spin={syncing} />} onClick={handleSync} loading={syncing}>
            立即同步
          </Button>
        </Space>
      </Space>

      <Card title="调度任务" size="small" style={{ marginBottom: 16 }}>
        {jobs.length === 0 ? (
          <Typography.Text type="secondary">暂无调度任务</Typography.Text>
        ) : (
          jobs.map((job) => (
            <Descriptions key={job.id} size="small" column={3} bordered style={{ marginBottom: 8 }}>
              <Descriptions.Item label="任务ID">{job.id}</Descriptions.Item>
              <Descriptions.Item label="触发规则">{job.trigger}</Descriptions.Item>
              <Descriptions.Item label="下次执行">
                {job.next_run && job.next_run !== "None" ? dayjs(job.next_run).format("YYYY-MM-DD HH:mm:ss") : "-"}
              </Descriptions.Item>
            </Descriptions>
          ))
        )}
      </Card>

      <Card title="同步日志" size="small">
        <Table
          rowKey="id"
          columns={logColumns}
          dataSource={logs}
          size="small"
          pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
          loading={loading}
        />
      </Card>
    </div>
  );
}
