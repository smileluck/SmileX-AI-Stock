import { useState } from "react";
import { Menu } from "antd";
import {
  DashboardOutlined,
  ReadOutlined,
  StockOutlined,
  SettingOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
  FieldTimeOutlined,
  FundOutlined,
  BulbOutlined,
  RobotOutlined,
  MessageOutlined,
  PieChartOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";

const menuItems = [
  {
    key: "/market",
    icon: <FundOutlined />,
    label: "大盘",
    children: [
      { key: "/market", icon: <DashboardOutlined />, label: "大盘概览" },
      { key: "/market/analysis", icon: <BulbOutlined />, label: "AI 分析" },
      { key: "/market/history", icon: <HistoryOutlined />, label: "历史大盘" },
    ],
  },
  { key: "/news", icon: <ReadOutlined />, label: "资讯聚合" },
  {
    key: "/sector",
    icon: <PieChartOutlined />,
    label: "行业板块",
    children: [
      { key: "/sector/today", icon: <DashboardOutlined />, label: "今日板块" },
      { key: "/sector/history", icon: <HistoryOutlined />, label: "历史板块" },
    ],
  },
  { key: "/scheduler", icon: <FieldTimeOutlined />, label: "定时任务" },
  {
    key: "/stock",
    icon: <StockOutlined />,
    label: "个股",
    children: [
      { key: "/stock/overview", icon: <DashboardOutlined />, label: "分析总览" },
      { key: "/stock/limit-up", icon: <ThunderboltOutlined />, label: "今日涨停" },
      { key: "/stock/recommendation", icon: <BulbOutlined />, label: "今日推荐" },
      { key: "/stock/history", icon: <HistoryOutlined />, label: "历史推荐" },
    ],
  },
  { key: "/strategy", icon: <ExperimentOutlined />, label: "策略管理" },
  { key: "/backtest", icon: <BarChartOutlined />, label: "策略回测" },
  {
    key: "/ai-assistant",
    icon: <RobotOutlined />,
    label: "AI助手",
    children: [
      { key: "/ai-assistant/llm-config", icon: <SettingOutlined />, label: "LLM配置" },
      { key: "/ai-assistant/chat", icon: <MessageOutlined />, label: "AI对话" },
    ],
  },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [openKeys, setOpenKeys] = useState<string[]>(() => {
    if (location.pathname.startsWith("/market")) return ["/market"];
    if (location.pathname.startsWith("/sector")) return ["/sector"];
    if (location.pathname.startsWith("/stock")) return ["/stock"];
    if (location.pathname.startsWith("/ai-assistant")) return ["/ai-assistant"];
    return [];
  });

  return (
    <Menu
      mode="inline"
      selectedKeys={[location.pathname]}
      openKeys={openKeys}
      onOpenChange={setOpenKeys}
      items={menuItems}
      onClick={({ key }) => navigate(key)}
      style={{ height: "100%", borderRight: 0 }}
    />
  );
}
